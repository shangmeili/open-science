//! App-owned natural-parameter survival evaluator; no R or Python dependency.

use std::collections::HashMap;
use std::f64::consts::{PI, SQRT_2};

const EPS: f64 = 2.0e-14;
const FPMIN: f64 = 1.0e-300;
const MAX_ITER: usize = 10_000;

pub(crate) fn curve(
    family: &str,
    p: &HashMap<String, f64>,
    time: f64,
) -> Result<(f64, Option<f64>), String> {
    if !time.is_finite() || time < 0.0 {
        return Err("time must be finite and non-negative".into());
    }
    validate(family, p)?;
    if time == 0.0 {
        return Ok((1.0, None));
    }
    let (survival, hazard) = match family {
        "exponential" => ((-p["rate"] * time).exp(), p["rate"]),
        "weibull" => {
            let power = (time / p["scale"]).powf(p["shape"]);
            ((-power).exp(), p["shape"] * power / time)
        }
        "gompertz" => {
            let scaled = p["shape"] * time;
            let exprel = if scaled == 0.0 {
                1.0
            } else {
                scaled.exp_m1() / scaled
            };
            ((-p["rate"] * time * exprel).exp(), p["rate"] * scaled.exp())
        }
        "gamma" => {
            let x = p["rate"] * time;
            let survival = gamma_q(p["shape"], x)?;
            let log_density = p["shape"] * p["rate"].ln() + (p["shape"] - 1.0) * time.ln()
                - x
                - log_gamma(p["shape"]);
            (survival, hazard(log_density.exp(), survival)?)
        }
        "lognormal" => {
            let z = (time.ln() - p["meanlog"]) / p["sdlog"];
            let survival = 0.5 * erfc(z / SQRT_2);
            let density = (-0.5 * z * z).exp() / (time * p["sdlog"] * (2.0 * PI).sqrt());
            (survival, hazard(density, survival)?)
        }
        "loglogistic" => {
            let log_odds = p["shape"] * (time.ln() - p["scale"].ln());
            let survival = inverse_one_plus_exp(log_odds);
            (survival, p["shape"] * (1.0 - survival) / time)
        }
        "generalized_gamma" => {
            let (survival, density) = generalized_gamma(p, time)?;
            (survival, hazard(density, survival)?)
        }
        "generalized_f" => {
            let (survival, density) = generalized_f(p, time)?;
            (survival, hazard(density, survival)?)
        }
        _ => return Err(format!("unsupported survival family {family}")),
    };
    if !survival.is_finite()
        || !(0.0..=1.0).contains(&survival)
        || !hazard.is_finite()
        || hazard < 0.0
    {
        return Err(format!("{family} evaluation is outside its admitted range"));
    }
    Ok((survival.clamp(0.0, 1.0), Some(hazard)))
}

fn validate(family: &str, p: &HashMap<String, f64>) -> Result<(), String> {
    let (required, positive): (&[&str], &[&str]) = match family {
        "exponential" => (&["rate"], &["rate"]),
        "weibull" => (&["shape", "scale"], &["shape", "scale"]),
        "gompertz" => (&["shape", "rate"], &["rate"]),
        "gamma" => (&["shape", "rate"], &["shape", "rate"]),
        "generalized_gamma" => (&["mu", "sigma", "Q"], &["sigma"]),
        "generalized_f" => (&["mu", "sigma", "Q", "P"], &["sigma"]),
        "lognormal" => (&["meanlog", "sdlog"], &["sdlog"]),
        "loglogistic" => (&["shape", "scale"], &["shape", "scale"]),
        _ => return Err(format!("unsupported survival family {family}")),
    };
    if p.len() != required.len()
        || required
            .iter()
            .any(|name| !p.get(*name).is_some_and(|v| v.is_finite()))
        || positive.iter().any(|name| p[*name] <= 0.0)
        || (family == "generalized_f" && p["P"] < 0.0)
    {
        return Err(format!(
            "{family} parameters violate the natural parameterization"
        ));
    }
    Ok(())
}

fn generalized_gamma(p: &HashMap<String, f64>, time: f64) -> Result<(f64, f64), String> {
    let z0 = (time.ln() - p["mu"]) / p["sigma"];
    if p["Q"] == 0.0 {
        return Ok((
            0.5 * erfc(z0 / SQRT_2),
            (-0.5 * z0 * z0).exp() / (time * p["sigma"] * (2.0 * PI).sqrt()),
        ));
    }
    let shape = 1.0 / (p["Q"] * p["Q"]);
    let log_argument = p["Q"] * z0 + shape.ln();
    let argument = if log_argument < 709.0 {
        log_argument.exp()
    } else {
        f64::INFINITY
    };
    let survival = if p["Q"] > 0.0 {
        gamma_q(shape, argument)?
    } else {
        gamma_p(shape, argument)?
    };
    let log_density = p["Q"].abs().ln() + shape * log_argument
        - argument
        - p["sigma"].ln()
        - time.ln()
        - log_gamma(shape);
    Ok((
        survival,
        if log_density > -746.0 {
            log_density.exp()
        } else {
            0.0
        },
    ))
}

fn generalized_f(p: &HashMap<String, f64>, time: f64) -> Result<(f64, f64), String> {
    if p["P"] == 0.0 {
        return generalized_gamma(p, time);
    }
    let total = p["Q"] * p["Q"] + 2.0 * p["P"];
    let delta = total.sqrt();
    let plus = total + p["Q"] * delta;
    let minus = total - p["Q"] * delta;
    let s1 = if plus.abs() < minus.abs() {
        minus / (p["P"] * total)
    } else {
        2.0 / plus
    };
    let s2 = if minus.abs() < plus.abs() {
        plus / (p["P"] * total)
    } else {
        2.0 / minus
    };
    let log_ratio = (s1 / s2).ln() + delta * (time.ln() - p["mu"]) / p["sigma"];
    let x = inverse_one_plus_exp(log_ratio);
    let survival = if log_ratio < 0.0 {
        1.0 - regularized_beta(inverse_one_plus_exp(-log_ratio), s1, s2)?
    } else {
        regularized_beta(x, s2, s1)?
    };
    let log_x = -softplus(log_ratio);
    let log_y = -softplus(-log_ratio);
    let log_density = delta.ln()
        - p["sigma"].ln()
        - time.ln()
        - (log_gamma(s1) + log_gamma(s2) - log_gamma(s1 + s2))
        + s1 * log_y
        + s2 * log_x;
    Ok((
        survival,
        if log_density > -746.0 {
            log_density.exp()
        } else {
            0.0
        },
    ))
}

fn gamma_p(a: f64, x: f64) -> Result<f64, String> {
    if x == 0.0 {
        return Ok(0.0);
    }
    if x.is_infinite() {
        return Ok(1.0);
    }
    if x >= a + 1.0 {
        return Ok(1.0 - gamma_q(a, x)?);
    }
    let (mut term, mut total, mut denominator) = (1.0 / a, 1.0 / a, a);
    for _ in 0..MAX_ITER {
        denominator += 1.0;
        term *= x / denominator;
        total += term;
        if term.abs() <= total.abs() * EPS {
            return unit(total * (-x + a * x.ln() - log_gamma(a)).exp());
        }
    }
    Err("regularized gamma series did not converge".into())
}

fn gamma_q(a: f64, x: f64) -> Result<f64, String> {
    if x == 0.0 {
        return Ok(1.0);
    }
    if x.is_infinite() {
        return Ok(0.0);
    }
    if x < a + 1.0 {
        return Ok(1.0 - gamma_p(a, x)?);
    }
    let mut b = x + 1.0 - a;
    let mut c = 1.0 / FPMIN;
    let mut d = 1.0 / b.abs().max(FPMIN) * if b < 0.0 { -1.0 } else { 1.0 };
    let mut result = d;
    for index in 1..=MAX_ITER {
        let coefficient = -(index as f64) * (index as f64 - a);
        b += 2.0;
        d = coefficient * d + b;
        if d.abs() < FPMIN {
            d = FPMIN;
        }
        c = b + coefficient / c;
        if c.abs() < FPMIN {
            c = FPMIN;
        }
        d = 1.0 / d;
        let delta = d * c;
        result *= delta;
        if (delta - 1.0).abs() <= EPS {
            return unit((-x + a * x.ln() - log_gamma(a)).exp() * result);
        }
    }
    Err("regularized gamma fraction did not converge".into())
}

fn regularized_beta(x: f64, a: f64, b: f64) -> Result<f64, String> {
    if x == 0.0 {
        return Ok(0.0);
    }
    if x == 1.0 {
        return Ok(1.0);
    }
    let front =
        (log_gamma(a + b) - log_gamma(a) - log_gamma(b) + a * x.ln() + b * (-x).ln_1p()).exp();
    if x < (a + 1.0) / (a + b + 2.0) {
        unit(front * beta_fraction(a, b, x)? / a)
    } else {
        unit(1.0 - front * beta_fraction(b, a, 1.0 - x)? / b)
    }
}

fn beta_fraction(a: f64, b: f64, x: f64) -> Result<f64, String> {
    let (qab, qap, qam) = (a + b, a + 1.0, a - 1.0);
    let mut c = 1.0;
    let mut d = 1.0 - qab * x / qap;
    if d.abs() < FPMIN {
        d = FPMIN;
    }
    d = 1.0 / d;
    let mut result = d;
    for index in 1..=MAX_ITER {
        let i = index as f64;
        let doubled = 2.0 * i;
        let mut coefficient = i * (b - i) * x / ((qam + doubled) * (a + doubled));
        d = 1.0 + coefficient * d;
        if d.abs() < FPMIN {
            d = FPMIN;
        }
        c = 1.0 + coefficient / c;
        if c.abs() < FPMIN {
            c = FPMIN;
        }
        d = 1.0 / d;
        result *= d * c;
        coefficient = -(a + i) * (qab + i) * x / ((a + doubled) * (qap + doubled));
        d = 1.0 + coefficient * d;
        if d.abs() < FPMIN {
            d = FPMIN;
        }
        c = 1.0 + coefficient / c;
        if c.abs() < FPMIN {
            c = FPMIN;
        }
        d = 1.0 / d;
        let delta = d * c;
        result *= delta;
        if (delta - 1.0).abs() <= EPS {
            return Ok(result);
        }
    }
    Err("regularized beta fraction did not converge".into())
}

// Lanczos approximation, reflected below 0.5. All admitted calls are positive.
fn log_gamma(z: f64) -> f64 {
    const C: [f64; 9] = [
        0.9999999999998099,
        676.5203681218851,
        -1259.1392167224028,
        771.3234287776531,
        -176.6150291621406,
        12.507343278686905,
        -0.13857109526572012,
        9.984369578019572e-6,
        1.5056327351493116e-7,
    ];
    if z < 0.5 {
        return PI.ln() - (PI * z).sin().ln() - log_gamma(1.0 - z);
    }
    let shifted = z - 1.0;
    let mut x = C[0];
    for (index, coefficient) in C.iter().enumerate().skip(1) {
        x += coefficient / (shifted + index as f64);
    }
    let t = shifted + 7.5;
    0.5 * (2.0 * PI).ln() + (shifted + 0.5) * t.ln() - t + x.ln()
}

fn erfc(x: f64) -> f64 {
    let squared = x * x;
    if x >= 0.0 {
        gamma_q(0.5, squared).expect("positive regularized gamma arguments")
    } else {
        1.0 + gamma_p(0.5, squared).expect("positive regularized gamma arguments")
    }
}

fn inverse_one_plus_exp(value: f64) -> f64 {
    if value >= 0.0 {
        let scaled = if value < 746.0 { (-value).exp() } else { 0.0 };
        scaled / (1.0 + scaled)
    } else {
        let scaled = if value > -746.0 { value.exp() } else { 0.0 };
        1.0 / (1.0 + scaled)
    }
}

fn softplus(value: f64) -> f64 {
    if value > 0.0 {
        value + (-value).exp().ln_1p()
    } else {
        value.exp().ln_1p()
    }
}

fn hazard(density: f64, survival: f64) -> Result<f64, String> {
    if survival <= 0.0 {
        Err("hazard is not finite after survival underflow".into())
    } else {
        Ok(density / survival)
    }
}

fn unit(value: f64) -> Result<f64, String> {
    if !value.is_finite() || !(-1e-12..=1.0 + 1e-12).contains(&value) {
        Err("special function result outside [0,1]".into())
    } else {
        Ok(value.clamp(0.0, 1.0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn eight_family_reference_values_are_stable() {
        let cases = [
            ("exponential", vec![("rate", 0.2)], 0.5488116360940264, 0.2),
            (
                "weibull",
                vec![("shape", 1.5), ("scale", 4.0)],
                0.5222969135825415,
                0.3247595264191645,
            ),
            (
                "gompertz",
                vec![("shape", -0.05), ("rate", 0.2)],
                0.5728289666761843,
                0.17214159528501158,
            ),
            (
                "gamma",
                vec![("shape", 2.5), ("rate", 0.7)],
                0.5209949534314058,
                0.3766507649696241,
            ),
            (
                "lognormal",
                vec![("meanlog", 1.2), ("sdlog", 0.8)],
                0.5504247856043497,
                0.2995801922384905,
            ),
            (
                "loglogistic",
                vec![("shape", 1.7), ("scale", 3.2)],
                0.5274013900048466,
                0.26780587899725355,
            ),
            (
                "generalized_gamma",
                vec![("mu", 1.0), ("sigma", 0.7), ("Q", -0.6)],
                0.525445650280221,
                0.347534536573228,
            ),
            (
                "generalized_f",
                vec![("mu", 1.0), ("sigma", 0.8), ("Q", -0.3), ("P", 0.9)],
                0.49721403432450284,
                0.29549220665380965,
            ),
        ];
        for (family, values, expected_survival, expected_hazard) in cases {
            let parameters = values.into_iter().map(|(k, v)| (k.to_owned(), v)).collect();
            let (survival, hazard) = curve(family, &parameters, 3.0).unwrap();
            assert!(
                (survival - expected_survival).abs() < 2e-7,
                "{family} survival"
            );
            assert!(
                (hazard.unwrap() - expected_hazard).abs() < 2e-7,
                "{family} hazard"
            );
        }
    }
}
