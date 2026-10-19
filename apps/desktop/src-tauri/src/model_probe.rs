use serde::Serialize;
use std::io::Read;
use std::time::Duration;

const MAX_MODEL_LIST_BYTES: u64 = 1_048_576;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ProbedModel {
    pub id: String,
    pub context: Option<u64>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ProbeResult {
    pub base_url: String,
    pub models: Vec<ProbedModel>,
}

#[tauri::command]
pub async fn probe_endpoint_models(
    base_url: String,
    api_key: Option<String>,
    kind: String,
) -> Result<ProbeResult, String> {
    tauri::async_runtime::spawn_blocking(move || probe(&base_url, api_key.as_deref(), &kind))
        .await
        .map_err(|error| format!("model probe task failed: {error}"))?
}

fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .user_agent("AI4HEOR model endpoint probe")
        .timeout(Duration::from_secs(5))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|error| format!("could not create HTTP client: {error}"))
}

fn probe(base_url: &str, api_key: Option<&str>, kind: &str) -> Result<ProbeResult, String> {
    let base = base_url.trim().trim_end_matches('/');
    if base.is_empty() {
        return Err("Base URL is empty".into());
    }
    let list = |candidate: &str| match kind {
        "anthropic" => probe_anthropic(candidate, api_key),
        _ => probe_openai(candidate, api_key),
    };
    match list(base) {
        Ok(models) => Ok(ProbeResult {
            base_url: base.into(),
            models,
        }),
        Err(original) if !base.ends_with("/v1") => {
            let corrected = format!("{base}/v1");
            list(&corrected)
                .map(|models| ProbeResult {
                    base_url: corrected,
                    models,
                })
                .map_err(|_| original)
        }
        Err(error) => Err(error),
    }
}

fn response_text(response: reqwest::blocking::Response) -> Result<String, String> {
    let response = response
        .error_for_status()
        .map_err(|error| format!("could not list models: {error}"))?;
    if response
        .content_length()
        .is_some_and(|length| length > MAX_MODEL_LIST_BYTES)
    {
        return Err("model list response exceeded 1 MiB".into());
    }
    let mut limited = response.take(MAX_MODEL_LIST_BYTES + 1);
    let mut bytes = Vec::new();
    limited
        .read_to_end(&mut bytes)
        .map_err(|error| format!("could not read the model list: {error}"))?;
    if bytes.len() as u64 > MAX_MODEL_LIST_BYTES {
        return Err("model list response exceeded 1 MiB".into());
    }
    String::from_utf8(bytes).map_err(|error| format!("model list was not UTF-8: {error}"))
}

fn probe_openai(base: &str, api_key: Option<&str>) -> Result<Vec<ProbedModel>, String> {
    let mut request = client()?.get(format!("{base}/models"));
    if let Some(key) = api_key.filter(|key| !key.is_empty()) {
        request = request.bearer_auth(key);
    }
    parse_models(&response_text(
        request
            .send()
            .map_err(|error| format!("could not list models: {error}"))?,
    )?)
}

fn probe_anthropic(base: &str, api_key: Option<&str>) -> Result<Vec<ProbedModel>, String> {
    let mut request = client()?
        .get(format!("{base}/models"))
        .header("anthropic-version", "2023-06-01");
    if let Some(key) = api_key.filter(|key| !key.is_empty()) {
        request = request.header("x-api-key", key);
    }
    parse_models(&response_text(
        request
            .send()
            .map_err(|error| format!("could not list models: {error}"))?,
    )?)
}

fn parse_models(body: &str) -> Result<Vec<ProbedModel>, String> {
    let value: serde_json::Value =
        serde_json::from_str(body).map_err(|error| format!("model list was not JSON: {error}"))?;
    let list = value
        .get("data")
        .and_then(serde_json::Value::as_array)
        .or_else(|| value.as_array())
        .ok_or("model list had no data array")?;
    let models: Vec<ProbedModel> = list
        .iter()
        .filter_map(|model| {
            let id = model.get("id")?.as_str()?.to_owned();
            let context = ["context_length", "max_model_len", "max_context_length"]
                .iter()
                .find_map(|key| model.get(*key).and_then(serde_json::Value::as_u64));
            Some(ProbedModel { id, context })
        })
        .collect();
    if models.is_empty() {
        return Err("the endpoint listed no models".into());
    }
    Ok(models)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn serve(routes: Vec<(&'static str, &'static str)>) -> String {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        std::thread::spawn(move || {
            for _ in 0..4 {
                let Ok((mut stream, _)) = listener.accept() else {
                    return;
                };
                let mut buffer = [0_u8; 4096];
                let count = stream.read(&mut buffer).unwrap_or(0);
                let request = String::from_utf8_lossy(&buffer[..count]);
                let path = request.split_whitespace().nth(1).unwrap_or("");
                let body = routes
                    .iter()
                    .find(|(prefix, _)| path.starts_with(prefix))
                    .map(|(_, body)| *body);
                let response = match body {
                    Some(body) => format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len()),
                    None => "HTTP/1.1 404 Not Found\r\ncontent-length: 0\r\nconnection: close\r\n\r\n".into(),
                };
                let _ = stream.write_all(response.as_bytes());
            }
        });
        base
    }

    #[test]
    fn parses_context_fields() {
        let models =
            parse_models(r#"{"data":[{"id":"vllm","max_model_len":32768},{"id":"plain"}]}"#)
                .unwrap();
        assert_eq!(models[0].context, Some(32768));
        assert_eq!(models[1].context, None);
    }

    #[test]
    fn appends_v1_only_when_it_serves_models() {
        let base = serve(vec![
            ("/v1/models", r#"{"data":[{"id":"gpt-compatible"}]}"#),
            ("/models", "<html></html>"),
        ]);
        let result = probe(&base, Some("secret"), "openai").unwrap();
        assert_eq!(result.base_url, format!("{base}/v1"));
        assert_eq!(result.models[0].id, "gpt-compatible");
    }

    #[test]
    fn preserves_an_explicit_v1_base() {
        let base = serve(vec![(
            "/v1/models",
            r#"{"data":[{"id":"claude-compatible"}]}"#,
        )]);
        let result = probe(&format!("{base}/v1"), Some("secret"), "anthropic").unwrap();
        assert_eq!(result.base_url, format!("{base}/v1"));
    }
}
