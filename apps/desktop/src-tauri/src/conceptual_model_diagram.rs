//! App-owned conceptual-model diagram export.
//!
//! The conceptual-model JSON remains the scientific review contract. This
//! module accepts only node coordinates, then renders the exact current states
//! and transitions as deterministic SVG and editable GraphML.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::io::Write;
use std::path::{Component, Path};
use tauri::AppHandle;

pub const MODEL_PATH: &str = "heor/conceptual-model.json";
pub const LAYOUT_PATH: &str = "deliverables/conceptual-model-layout.json";
pub const SVG_PATH: &str = "deliverables/conceptual-model.svg";
pub const GRAPHML_PATH: &str = "deliverables/conceptual-model.graphml";
pub const AUDIT_PATH: &str = "deliverables/conceptual-model.audit.json";
const ENGINE_VERSION: &str = "0.1.0";
const MODEL_CAP_BYTES: u64 = 5 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 5 * 1024 * 1024;
const MAX_STATES: usize = 24;
const MAX_TRANSITIONS: usize = 128;
const MIN_X: i32 = 120;
const MAX_X: i32 = 1160;
const MIN_Y: i32 = 240;
const MAX_Y: i32 = 540;
const CANVAS_WIDTH: i32 = 1280;
const CANVAS_HEIGHT: i32 = 760;
const NODE_WIDTH: f64 = 220.0;
const NODE_HEIGHT: f64 = 92.0;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DiagramNodePosition {
    pub state_id: String,
    pub x: i32,
    pub y: i32,
}

#[derive(Clone, Debug, Deserialize)]
struct ConceptualModel {
    model_id: String,
    analysis_id: String,
    status: String,
    objective: String,
    care_pathway: Vec<String>,
    model_type: ModelType,
    states: Vec<ModelState>,
    transitions: Vec<ModelTransition>,
    structural_assumptions: Vec<StructuralAssumption>,
    structural_alternatives: Vec<StructuralAlternative>,
}

#[derive(Clone, Debug, Deserialize)]
struct ModelType {
    proposed: String,
}

#[derive(Clone, Debug, Deserialize)]
struct ModelState {
    id: String,
    label: String,
    definition: String,
    absorbing: bool,
}

#[derive(Clone, Debug, Deserialize)]
struct ModelTransition {
    id: String,
    from: String,
    to: String,
    trigger: String,
}

#[derive(Clone, Debug, Deserialize)]
struct StructuralAssumption {
    id: String,
    statement: String,
    status: String,
}

#[derive(Clone, Debug, Deserialize)]
struct StructuralAlternative {
    id: String,
    description: String,
    expected_impact: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
struct LayoutRecord {
    schema_version: String,
    model_id: String,
    conceptual_model_path: String,
    conceptual_model_sha256: String,
    positions: Vec<DiagramNodePosition>,
    human_review_status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    model_id: String,
    conceptual_model_path: String,
    conceptual_model_sha256: String,
    layout_path: String,
    layout_sha256: String,
    svg_path: String,
    svg_sha256: String,
    graphml_path: String,
    graphml_sha256: String,
    state_count: usize,
    transition_count: usize,
    human_review_status: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConceptualModelDiagramAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub outputs_current: bool,
    pub status: &'static str,
    pub model_id: String,
    pub model_path: &'static str,
    pub layout_path: &'static str,
    pub svg_path: &'static str,
    pub graphml_path: &'static str,
    pub audit_path: &'static str,
    pub conceptual_model_sha256: String,
    pub layout_sha256: Option<String>,
    pub svg_sha256: Option<String>,
    pub graphml_sha256: Option<String>,
    pub state_count: usize,
    pub transition_count: usize,
    pub positions: Vec<DiagramNodePosition>,
    pub human_review_status: String,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

struct LoadedModel {
    model: ConceptualModel,
    raw: Vec<u8>,
    sha256: String,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn bounded_text(value: &str, label: &str) -> Result<(), String> {
    let count = value.chars().count();
    if value.trim().is_empty() || count > 2_000 {
        return Err(format!("{label} must contain 1 to 2000 characters"));
    }
    if value
        .chars()
        .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
    {
        return Err(format!("{label} contains an unsupported control character"));
    }
    Ok(())
}

fn load_model_bytes(raw: &[u8]) -> Result<ConceptualModel, String> {
    if raw.len() as u64 > MODEL_CAP_BYTES {
        return Err(format!("{MODEL_PATH} exceeds the 5 MiB diagram limit"));
    }
    let audit = crate::heor_artifacts::audit_conceptual_model_bytes(raw)?;
    if !audit.complete {
        return Err(format!(
            "conceptual model is not ready for diagram export: {}",
            audit.errors.join("; ")
        ));
    }
    let model: ConceptualModel = serde_json::from_slice(raw)
        .map_err(|error| format!("conceptual model cannot be rendered: {error}"))?;
    if model.states.len() > MAX_STATES {
        return Err(format!("conceptual model exceeds {MAX_STATES} states"));
    }
    if model.transitions.len() > MAX_TRANSITIONS {
        return Err(format!(
            "conceptual model exceeds {MAX_TRANSITIONS} transitions"
        ));
    }
    for (index, state) in model.states.iter().enumerate() {
        bounded_text(&state.label, &format!("states[{index}].label"))?;
        bounded_text(&state.definition, &format!("states[{index}].definition"))?;
    }
    for (index, transition) in model.transitions.iter().enumerate() {
        bounded_text(
            &transition.trigger,
            &format!("transitions[{index}].trigger"),
        )?;
    }
    bounded_text(&model.objective, "objective")?;
    Ok(model)
}

fn normalized_positions(
    model: &ConceptualModel,
    positions: &[DiagramNodePosition],
) -> Result<Vec<DiagramNodePosition>, String> {
    if positions.len() != model.states.len() {
        return Err("diagram layout must include every state exactly once".into());
    }
    let mut by_id = HashMap::new();
    for position in positions {
        if !model
            .states
            .iter()
            .any(|state| state.id == position.state_id)
        {
            return Err(format!(
                "diagram layout references unknown state {}",
                position.state_id
            ));
        }
        if by_id.insert(position.state_id.as_str(), position).is_some() {
            return Err("diagram layout state IDs must be unique".into());
        }
        if !(MIN_X..=MAX_X).contains(&position.x) || !(MIN_Y..=MAX_Y).contains(&position.y) {
            return Err(format!(
                "diagram coordinates must stay within x={MIN_X}..{MAX_X}, y={MIN_Y}..{MAX_Y}"
            ));
        }
    }
    model
        .states
        .iter()
        .map(|state| {
            by_id
                .get(state.id.as_str())
                .map(|position| (*position).clone())
                .ok_or_else(|| "diagram layout must include every state exactly once".into())
        })
        .collect()
}

fn endpoint(from: (f64, f64), to: (f64, f64), reverse: bool) -> (f64, f64) {
    let dx = to.0 - from.0;
    let dy = to.1 - from.1;
    let scale_x = if dx.abs() < f64::EPSILON {
        f64::INFINITY
    } else {
        (NODE_WIDTH / 2.0) / dx.abs()
    };
    let scale_y = if dy.abs() < f64::EPSILON {
        f64::INFINITY
    } else {
        (NODE_HEIGHT / 2.0) / dy.abs()
    };
    let scale = scale_x.min(scale_y);
    if reverse {
        (to.0 - dx * scale, to.1 - dy * scale)
    } else {
        (from.0 + dx * scale, from.1 + dy * scale)
    }
}

fn short_lines(value: &str, maximum_lines: usize, width: usize) -> Vec<String> {
    let compact = value.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut lines = Vec::new();
    let mut current = String::new();
    for character in compact.chars() {
        if current.chars().count() >= width {
            lines.push(current);
            current = String::new();
            if lines.len() == maximum_lines {
                break;
            }
        }
        current.push(character);
    }
    if lines.len() < maximum_lines && !current.is_empty() {
        lines.push(current);
    }
    if compact.chars().count() > maximum_lines * width {
        if let Some(last) = lines.last_mut() {
            while last.chars().count() > width.saturating_sub(1) {
                last.pop();
            }
            last.push('…');
        }
    }
    lines
}

fn render_diagram(
    model_raw: &[u8],
    positions: &[DiagramNodePosition],
) -> Result<(Vec<u8>, Vec<u8>), String> {
    let model = load_model_bytes(model_raw)?;
    let positions = normalized_positions(&model, positions)?;
    let position_map = positions
        .iter()
        .map(|position| {
            (
                position.state_id.as_str(),
                (position.x as f64, position.y as f64),
            )
        })
        .collect::<HashMap<_, _>>();
    let model_hash = sha256(model_raw);

    let mut svg = String::new();
    svg.push_str("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
    svg.push_str(&format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{CANVAS_WIDTH}\" height=\"{CANVAS_HEIGHT}\" viewBox=\"0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}\" role=\"img\" aria-labelledby=\"diagram-title diagram-desc\">\n"
    ));
    svg.push_str(&format!(
        "<title id=\"diagram-title\">{}</title><desc id=\"diagram-desc\">AI4HEOR conceptual model {}. Source {} SHA-256 {}.</desc>\n",
        xml(&model.objective), xml(&model.model_id), MODEL_PATH, model_hash
    ));
    svg.push_str(&format!(
        "<metadata>model_id={};analysis_id={};status={};source={};sha256={};generator=ai4heor-conceptual-diagram-{ENGINE_VERSION}</metadata>\n",
        xml(&model.model_id), xml(&model.analysis_id), xml(&model.status), MODEL_PATH, model_hash
    ));
    svg.push_str("<defs><marker id=\"arrow\" markerWidth=\"9\" markerHeight=\"7\" refX=\"8\" refY=\"3.5\" orient=\"auto\"><path d=\"M0,0 L9,3.5 L0,7 Z\" fill=\"#365f7a\"/></marker><filter id=\"shadow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\"><feDropShadow dx=\"0\" dy=\"2\" stdDeviation=\"3\" flood-color=\"#132238\" flood-opacity=\"0.12\"/></filter></defs>\n");
    svg.push_str("<rect width=\"1280\" height=\"760\" fill=\"#fbfaf7\"/><text x=\"60\" y=\"52\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"28\" font-weight=\"700\" fill=\"#172033\">概念模型 / Conceptual model</text>\n");
    svg.push_str(&format!("<text x=\"60\" y=\"82\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"15\" fill=\"#556070\">{} · {}</text>\n", xml(&short_lines(&model.objective, 1, 85).join("")), xml(&model.model_type.proposed)));
    svg.push_str(&format!("<text x=\"1220\" y=\"50\" text-anchor=\"end\" font-family=\"JetBrains Mono, monospace\" font-size=\"10\" fill=\"#7a8491\">{}…</text>\n", &model_hash[..12]));

    for transition in &model.transitions {
        let Some(&from) = position_map.get(transition.from.as_str()) else {
            return Err(format!(
                "transition {} has no source position",
                transition.id
            ));
        };
        let Some(&to) = position_map.get(transition.to.as_str()) else {
            return Err(format!(
                "transition {} has no target position",
                transition.id
            ));
        };
        let transition_id = xml(&transition.id);
        let trigger_text = short_lines(&transition.trigger, 1, 22).join("");
        let trigger = xml(&trigger_text);
        let label_width = (trigger_text.chars().count() as f64 * 12.0 + 16.0).clamp(32.0, 116.0);
        if transition.from == transition.to {
            let left = from.0 - 62.0;
            let right = from.0 + 62.0;
            let top = from.1 - NODE_HEIGHT / 2.0;
            svg.push_str(&format!("<g data-transition-id=\"{transition_id}\"><path d=\"M {left:.1} {top:.1} C {left:.1} {:.1}, {right:.1} {:.1}, {right:.1} {top:.1}\" fill=\"none\" stroke=\"#6b7d8d\" stroke-width=\"2\" marker-end=\"url(#arrow)\"/><text x=\"{:.1}\" y=\"{:.1}\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"11\" fill=\"#536474\">{trigger}</text></g>\n", from.1 - 120.0, from.1 - 120.0, from.0, from.1 - 126.0));
        } else {
            let start = endpoint(from, to, false);
            let end = endpoint(from, to, true);
            let distance = ((end.0 - start.0).powi(2) + (end.1 - start.1).powi(2)).sqrt();
            if distance > NODE_WIDTH * 1.8 {
                let normal = (-(end.1 - start.1) / distance, (end.0 - start.0) / distance);
                let control = (
                    (start.0 + end.0) / 2.0 + normal.0 * 160.0,
                    (start.1 + end.1) / 2.0 + normal.1 * 160.0,
                );
                let label = (
                    (start.0 + 2.0 * control.0 + end.0) / 4.0,
                    (start.1 + 2.0 * control.1 + end.1) / 4.0,
                );
                svg.push_str(&format!("<g data-transition-id=\"{transition_id}\"><path d=\"M {:.1} {:.1} Q {:.1} {:.1} {:.1} {:.1}\" fill=\"none\" stroke=\"#365f7a\" stroke-width=\"2.2\" marker-end=\"url(#arrow)\"/><rect x=\"{:.1}\" y=\"{:.1}\" width=\"{label_width:.1}\" height=\"18\" rx=\"4\" fill=\"#fbfaf7\"/><text x=\"{:.1}\" y=\"{:.1}\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"11\" fill=\"#365f7a\">{trigger}</text></g>\n", start.0, start.1, control.0, control.1, end.0, end.1, label.0 - label_width / 2.0, label.1 - 13.0, label.0, label.1));
            } else {
                let mid = ((start.0 + end.0) / 2.0, (start.1 + end.1) / 2.0);
                svg.push_str(&format!("<g data-transition-id=\"{transition_id}\"><line x1=\"{:.1}\" y1=\"{:.1}\" x2=\"{:.1}\" y2=\"{:.1}\" stroke=\"#365f7a\" stroke-width=\"2.2\" marker-end=\"url(#arrow)\"/><rect x=\"{:.1}\" y=\"{:.1}\" width=\"{label_width:.1}\" height=\"18\" rx=\"4\" fill=\"#fbfaf7\"/><text x=\"{:.1}\" y=\"{:.1}\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"11\" fill=\"#365f7a\">{trigger}</text></g>\n", start.0, start.1, end.0, end.1, mid.0 - label_width / 2.0, mid.1 - 13.0, mid.0, mid.1));
            }
        }
    }

    for (state, position) in model.states.iter().zip(&positions) {
        let x = position.x as f64 - NODE_WIDTH / 2.0;
        let y = position.y as f64 - NODE_HEIGHT / 2.0;
        let stroke_width = if state.absorbing { 4 } else { 2 };
        let fill = if state.absorbing {
            "#f4ece9"
        } else {
            "#eef4f7"
        };
        svg.push_str(&format!("<g data-state-id=\"{}\" transform=\"translate({x:.1} {y:.1})\" filter=\"url(#shadow)\"><rect width=\"{NODE_WIDTH}\" height=\"{NODE_HEIGHT}\" rx=\"14\" fill=\"{fill}\" stroke=\"#2f5f78\" stroke-width=\"{stroke_width}\"/>", xml(&state.id)));
        if state.absorbing {
            svg.push_str(&format!("<rect x=\"7\" y=\"7\" width=\"{:.1}\" height=\"{:.1}\" rx=\"10\" fill=\"none\" stroke=\"#2f5f78\" stroke-width=\"1.5\"/>", NODE_WIDTH - 14.0, NODE_HEIGHT - 14.0));
        }
        let label_lines = short_lines(&state.label, 2, 13);
        for (line_index, line) in label_lines.iter().enumerate() {
            svg.push_str(&format!("<text x=\"110\" y=\"{}\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"17\" font-weight=\"700\" fill=\"#172033\">{}</text>", 31 + line_index * 18, xml(line)));
        }
        let definition = short_lines(&state.definition, 1, 24).join("");
        svg.push_str(&format!("<text x=\"110\" y=\"73\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"11\" fill=\"#596675\">{}</text></g>\n", xml(&definition)));
    }

    let pathway = model.care_pathway.join(" → ");
    let assumption_summary = model
        .structural_assumptions
        .iter()
        .map(|item| format!("{} [{}] {}", item.id, item.status, item.statement))
        .collect::<Vec<_>>()
        .join(" · ");
    let alternative_summary = model
        .structural_alternatives
        .iter()
        .map(|item| {
            format!(
                "{}: {} ({})",
                item.id, item.description, item.expected_impact
            )
        })
        .collect::<Vec<_>>()
        .join(" · ");
    svg.push_str(&format!("<rect x=\"60\" y=\"620\" width=\"1160\" height=\"82\" rx=\"12\" fill=\"#f1eee6\"/><text x=\"80\" y=\"647\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"12\" font-weight=\"700\" fill=\"#394452\">研究路径 / Care pathway</text><text x=\"80\" y=\"668\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"12\" fill=\"#53606d\">{}</text><text x=\"80\" y=\"689\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"10\" fill=\"#6a7480\">假设：{} · 备选：{}</text>\n", xml(&short_lines(&pathway, 1, 130).join("")), xml(&short_lines(&assumption_summary, 1, 70).join("")), xml(&short_lines(&alternative_summary, 1, 70).join(""))));
    svg.push_str("<text x=\"640\" y=\"735\" text-anchor=\"middle\" font-family=\"Inter, Source Han Sans CN, sans-serif\" font-size=\"10\" fill=\"#7a8491\">图形用于解释和复核；heor/conceptual-model.json 才是结构审查依据。节点位置变化不改变模型语义。</text></svg>\n");

    let mut graphml = String::new();
    graphml.push_str("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<graphml xmlns=\"http://graphml.graphdrawing.org/xmlns\">\n");
    for (id, target, name, kind) in [
        ("label", "node", "label", "string"),
        ("definition", "node", "definition", "string"),
        ("absorbing", "node", "absorbing", "boolean"),
        ("x", "node", "x", "int"),
        ("y", "node", "y", "int"),
        ("trigger", "edge", "trigger", "string"),
        ("source_sha256", "graph", "source_sha256", "string"),
        ("source_path", "graph", "source_path", "string"),
    ] {
        graphml.push_str(&format!(
            "<key id=\"{id}\" for=\"{target}\" attr.name=\"{name}\" attr.type=\"{kind}\"/>\n"
        ));
    }
    graphml.push_str(&format!("<graph id=\"{}\" edgedefault=\"directed\"><data key=\"source_path\">{MODEL_PATH}</data><data key=\"source_sha256\">{model_hash}</data>\n", xml(&model.model_id)));
    for (state, position) in model.states.iter().zip(&positions) {
        graphml.push_str(&format!("<node id=\"{}\"><data key=\"label\">{}</data><data key=\"definition\">{}</data><data key=\"absorbing\">{}</data><data key=\"x\">{}</data><data key=\"y\">{}</data></node>\n", xml(&state.id), xml(&state.label), xml(&state.definition), state.absorbing, position.x, position.y));
    }
    for transition in &model.transitions {
        graphml.push_str(&format!(
            "<edge id=\"{}\" source=\"{}\" target=\"{}\"><data key=\"trigger\">{}</data></edge>\n",
            xml(&transition.id),
            xml(&transition.from),
            xml(&transition.to),
            xml(&transition.trigger)
        ));
    }
    graphml.push_str("</graph></graphml>\n");

    if svg.len() > OUTPUT_CAP_BYTES || graphml.len() > OUTPUT_CAP_BYTES {
        return Err("generated conceptual-model diagram exceeds the 5 MiB output limit".into());
    }
    Ok((svg.into_bytes(), graphml.into_bytes()))
}

fn read_regular(workspace: &Path, relative: &str, cap: u64) -> Result<Vec<u8>, String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut current = root.clone();
    for component in Path::new(relative).components() {
        let Component::Normal(part) = component else {
            return Err(format!("{relative} is not a safe workspace-relative path"));
        };
        current.push(part);
        let metadata = std::fs::symlink_metadata(&current)
            .map_err(|error| format!("{relative} unavailable: {error}"))?;
        if metadata.file_type().is_symlink() {
            return Err(format!("{relative} traverses a symlink"));
        }
    }
    let canonical = current
        .canonicalize()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !canonical.starts_with(&root) {
        return Err(format!("{relative} resolves outside the workspace"));
    }
    let metadata = std::fs::metadata(&canonical)
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{relative} is not a bounded regular file"));
    }
    std::fs::read(&canonical).map_err(|error| format!("{relative} unavailable: {error}"))
}

fn load_model_at(workspace: &Path) -> Result<LoadedModel, String> {
    let raw = read_regular(workspace, MODEL_PATH, MODEL_CAP_BYTES)?;
    let model = load_model_bytes(&raw)?;
    let sha256 = sha256(&raw);
    Ok(LoadedModel { model, raw, sha256 })
}

fn read_optional(workspace: &Path, relative: &str, cap: u64) -> Result<Option<Vec<u8>>, String> {
    match std::fs::symlink_metadata(workspace.join(relative)) {
        Ok(_) => read_regular(workspace, relative, cap).map(Some),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("{relative} unavailable: {error}")),
    }
}

fn empty_audit() -> ConceptualModelDiagramAudit {
    ConceptualModelDiagramAudit {
        complete: false,
        ready_to_generate: false,
        outputs_current: false,
        status: "incomplete",
        model_id: String::new(),
        model_path: MODEL_PATH,
        layout_path: LAYOUT_PATH,
        svg_path: SVG_PATH,
        graphml_path: GRAPHML_PATH,
        audit_path: AUDIT_PATH,
        conceptual_model_sha256: String::new(),
        layout_sha256: None,
        svg_sha256: None,
        graphml_sha256: None,
        state_count: 0,
        transition_count: 0,
        positions: Vec::new(),
        human_review_status: "awaiting_human_review".into(),
        errors: Vec::new(),
        warnings: Vec::new(),
    }
}

fn valid_layout(
    model: &LoadedModel,
    raw: &[u8],
) -> Result<(LayoutRecord, Vec<DiagramNodePosition>), String> {
    let layout: LayoutRecord = serde_json::from_slice(raw)
        .map_err(|error| format!("{LAYOUT_PATH} is invalid: {error}"))?;
    if layout.schema_version != "0.1.0"
        || layout.model_id != model.model.model_id
        || layout.conceptual_model_path != MODEL_PATH
        || layout.human_review_status != "awaiting_human_review"
    {
        return Err(format!("{LAYOUT_PATH} does not match the diagram contract"));
    }
    let positions = normalized_positions(&model.model, &layout.positions)?;
    Ok((layout, positions))
}

fn audit_at(workspace: &Path) -> ConceptualModelDiagramAudit {
    let mut audit = empty_audit();
    let model = match load_model_at(workspace) {
        Ok(model) => model,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.complete = true;
    audit.ready_to_generate = true;
    audit.status = "ready_to_generate";
    audit.model_id = model.model.model_id.clone();
    audit.conceptual_model_sha256 = model.sha256.clone();
    audit.state_count = model.model.states.len();
    audit.transition_count = model.model.transitions.len();

    let layout_raw = match read_optional(workspace, LAYOUT_PATH, MODEL_CAP_BYTES) {
        Ok(raw) => raw,
        Err(error) => {
            audit.complete = false;
            audit.ready_to_generate = false;
            audit.status = "incomplete";
            audit.errors.push(error);
            return audit;
        }
    };
    let Some(layout_raw) = layout_raw else {
        return audit;
    };
    let (layout, positions) = match valid_layout(&model, &layout_raw) {
        Ok(value) => value,
        Err(error) => {
            audit.complete = false;
            audit.ready_to_generate = false;
            audit.status = "incomplete";
            audit.errors.push(error);
            return audit;
        }
    };
    audit.layout_sha256 = Some(sha256(&layout_raw));
    if layout.conceptual_model_sha256 != model.sha256 {
        audit.warnings.push(
            "The saved node layout belongs to an earlier conceptual-model version; arrange the current states before exporting."
                .into(),
        );
        return audit;
    }
    audit.positions = positions;

    let record_raw = match read_optional(workspace, AUDIT_PATH, MODEL_CAP_BYTES) {
        Ok(raw) => raw,
        Err(error) => {
            audit.warnings.push(error);
            return audit;
        }
    };
    let Some(record_raw) = record_raw else {
        return audit;
    };
    let record: GenerationRecord = match serde_json::from_slice(&record_raw) {
        Ok(record) => record,
        Err(error) => {
            audit
                .warnings
                .push(format!("{AUDIT_PATH} is invalid: {error}"));
            return audit;
        }
    };
    let svg = read_optional(workspace, SVG_PATH, OUTPUT_CAP_BYTES as u64)
        .ok()
        .flatten();
    let graphml = read_optional(workspace, GRAPHML_PATH, OUTPUT_CAP_BYTES as u64)
        .ok()
        .flatten();
    let current = record.schema_version == "0.1.0"
        && record.generator == "ai4heor-conceptual-model-diagram"
        && record.generator_version == ENGINE_VERSION
        && record.model_id == model.model.model_id
        && record.conceptual_model_path == MODEL_PATH
        && record.conceptual_model_sha256 == model.sha256
        && record.layout_path == LAYOUT_PATH
        && record.layout_sha256 == sha256(&layout_raw)
        && record.svg_path == SVG_PATH
        && svg
            .as_deref()
            .is_some_and(|raw| record.svg_sha256 == sha256(raw))
        && record.graphml_path == GRAPHML_PATH
        && graphml
            .as_deref()
            .is_some_and(|raw| record.graphml_sha256 == sha256(raw))
        && record.state_count == model.model.states.len()
        && record.transition_count == model.model.transitions.len()
        && record.human_review_status == "awaiting_human_review";
    if current {
        audit.outputs_current = true;
        audit.status = "current";
        audit.svg_sha256 = Some(record.svg_sha256);
        audit.graphml_sha256 = Some(record.graphml_sha256);
    }
    audit
}

fn existing_outputs_replaceable(workspace: &Path, new_layout: &[u8]) -> Result<(), String> {
    let record_raw = read_optional(workspace, AUDIT_PATH, MODEL_CAP_BYTES)?;
    let Some(record_raw) = record_raw else {
        for path in [SVG_PATH, GRAPHML_PATH] {
            if read_optional(workspace, path, OUTPUT_CAP_BYTES as u64)?.is_some() {
                return Err(format!(
                    "{path} already exists without an AI4HEOR generation record; move or rename it before exporting"
                ));
            }
        }
        if let Some(existing) = read_optional(workspace, LAYOUT_PATH, MODEL_CAP_BYTES)? {
            if existing != new_layout {
                return Err(format!(
                    "{LAYOUT_PATH} was not created by the current export; move or rename it before replacing the layout"
                ));
            }
        }
        return Ok(());
    };
    let record: GenerationRecord = serde_json::from_slice(&record_raw)
        .map_err(|error| format!("{AUDIT_PATH} cannot authorize replacement: {error}"))?;
    for (path, expected, cap) in [
        (LAYOUT_PATH, record.layout_sha256.as_str(), MODEL_CAP_BYTES),
        (
            SVG_PATH,
            record.svg_sha256.as_str(),
            OUTPUT_CAP_BYTES as u64,
        ),
        (
            GRAPHML_PATH,
            record.graphml_sha256.as_str(),
            OUTPUT_CAP_BYTES as u64,
        ),
    ] {
        if let Some(raw) = read_optional(workspace, path, cap)? {
            if sha256(&raw) != expected {
                return Err(format!(
                    "{path} changed outside AI4HEOR; move or rename it before exporting a replacement"
                ));
            }
        }
    }
    Ok(())
}

fn write_atomic(workspace: &Path, relative: &str, raw: &[u8]) -> Result<(), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let path = workspace.join(relative);
    let parent = path
        .parent()
        .ok_or_else(|| format!("{relative} has no parent directory"))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    let canonical_parent = parent
        .canonicalize()
        .map_err(|error| format!("{} unavailable: {error}", parent.display()))?;
    if !canonical_parent.starts_with(&root) {
        return Err(format!("{relative} resolves outside the workspace"));
    }
    if let Ok(metadata) = std::fs::symlink_metadata(&path) {
        if metadata.file_type().is_symlink() {
            return Err(format!("{relative} is a symbolic link"));
        }
    }
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("diagram"),
        std::process::id()
    ));
    let mut file = std::fs::File::create(&temporary)
        .map_err(|error| format!("cannot prepare {relative}: {error}"))?;
    file.write_all(raw)
        .and_then(|()| file.sync_all())
        .map_err(|error| format!("cannot write {relative}: {error}"))?;
    std::fs::rename(&temporary, &path)
        .map_err(|error| format!("cannot replace {relative}: {error}"))
}

fn generate_at(
    workspace: &Path,
    positions: Vec<DiagramNodePosition>,
) -> Result<ConceptualModelDiagramAudit, String> {
    let model = load_model_at(workspace)?;
    let positions = normalized_positions(&model.model, &positions)?;
    let layout = LayoutRecord {
        schema_version: "0.1.0".into(),
        model_id: model.model.model_id.clone(),
        conceptual_model_path: MODEL_PATH.into(),
        conceptual_model_sha256: model.sha256.clone(),
        positions: positions.clone(),
        human_review_status: "awaiting_human_review".into(),
    };
    let layout_raw = serde_json::to_vec_pretty(&layout)
        .map_err(|error| format!("cannot serialize diagram layout: {error}"))?;
    let (svg, graphml) = render_diagram(&model.raw, &positions)?;
    let record = GenerationRecord {
        schema_version: "0.1.0".into(),
        generator: "ai4heor-conceptual-model-diagram".into(),
        generator_version: ENGINE_VERSION.into(),
        model_id: model.model.model_id.clone(),
        conceptual_model_path: MODEL_PATH.into(),
        conceptual_model_sha256: model.sha256,
        layout_path: LAYOUT_PATH.into(),
        layout_sha256: sha256(&layout_raw),
        svg_path: SVG_PATH.into(),
        svg_sha256: sha256(&svg),
        graphml_path: GRAPHML_PATH.into(),
        graphml_sha256: sha256(&graphml),
        state_count: model.model.states.len(),
        transition_count: model.model.transitions.len(),
        human_review_status: "awaiting_human_review".into(),
    };
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize diagram audit: {error}"))?;
    if audit_at(workspace).outputs_current
        && read_optional(workspace, LAYOUT_PATH, MODEL_CAP_BYTES)?.as_deref()
            == Some(layout_raw.as_slice())
    {
        return Ok(audit_at(workspace));
    }
    existing_outputs_replaceable(workspace, &layout_raw)?;
    write_atomic(workspace, LAYOUT_PATH, &layout_raw)?;
    write_atomic(workspace, SVG_PATH, &svg)?;
    write_atomic(workspace, GRAPHML_PATH, &graphml)?;
    write_atomic(workspace, AUDIT_PATH, &record_raw)?;
    Ok(audit_at(workspace))
}

#[tauri::command(async)]
pub fn audit_conceptual_model_diagram(
    app: AppHandle,
) -> Result<ConceptualModelDiagramAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?))
}

#[tauri::command(async)]
pub fn generate_conceptual_model_diagram(
    app: AppHandle,
    positions: Vec<DiagramNodePosition>,
) -> Result<ConceptualModelDiagramAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?, positions)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn model_raw() -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "schema_version": "0.1.0",
            "model_id": "model-1",
            "analysis_id": "analysis-1",
            "status": "ready_for_human_review",
            "objective": "比较治疗策略的成本和 QALY",
            "scope": {
                "population": "Adults", "intervention": "A", "comparator": "B",
                "perspective": "Healthcare system", "time_horizon": "Lifetime",
                "outcomes": ["cost", "QALY"], "jurisdiction": "China",
                "decision_context": "Research"
            },
            "care_pathway": ["开始治疗", "疾病进展", "死亡"],
            "model_type": {"proposed": "cohort_state_transition", "rationale": "Adequate states"},
            "states": [
                {"id": "stable", "label": "稳定", "definition": "未进展", "absorbing": false},
                {"id": "progressed", "label": "进展", "definition": "疾病进展", "absorbing": false},
                {"id": "dead", "label": "死亡", "definition": "全因死亡", "absorbing": true}
            ],
            "transitions": [
                {"id": "stable-stable", "from": "stable", "to": "stable", "trigger": "维持"},
                {"id": "stable-progressed", "from": "stable", "to": "progressed", "trigger": "进展"},
                {"id": "stable-dead", "from": "stable", "to": "dead", "trigger": "死亡"},
                {"id": "progressed-progressed", "from": "progressed", "to": "progressed", "trigger": "维持"},
                {"id": "progressed-dead", "from": "progressed", "to": "dead", "trigger": "死亡"},
                {"id": "dead-dead", "from": "dead", "to": "dead", "trigger": "吸收"}
            ],
            "structural_assumptions": [{
                "id": "memoryless", "statement": "无记忆假设", "rationale": "模型结构", "status": "proposed"
            }],
            "structural_alternatives": [{
                "id": "alt", "description": "半马尔可夫", "rationale": "时间依赖", "expected_impact": "状态占用"
            }],
            "evidence_links": [{"claim": "Pathway", "source_ids": ["source-1"]}],
            "validation_plan": {
                "face": ["Expert review"], "internal": ["Boundary checks"], "external": ["Outcome comparison"]
            },
            "validation_questions": ["Are states exhaustive?"]
        }))
        .unwrap()
    }

    fn positions() -> Vec<DiagramNodePosition> {
        vec![
            DiagramNodePosition {
                state_id: "stable".into(),
                x: 180,
                y: 260,
            },
            DiagramNodePosition {
                state_id: "progressed".into(),
                x: 500,
                y: 260,
            },
            DiagramNodePosition {
                state_id: "dead".into(),
                x: 820,
                y: 260,
            },
        ]
    }

    #[test]
    fn deterministic_svg_and_graphml_preserve_exact_model_structure() {
        let first = render_diagram(&model_raw(), &positions()).unwrap();
        let second = render_diagram(&model_raw(), &positions()).unwrap();
        assert_eq!(first, second);
        let svg = String::from_utf8(first.0).unwrap();
        let graphml = String::from_utf8(first.1).unwrap();
        assert!(svg.contains("<svg"));
        assert!(svg.contains("稳定"));
        assert!(svg.contains("data-state-id=\"dead\""));
        assert!(svg.contains("data-transition-id=\"stable-progressed\""));
        assert!(!svg.contains("<script"));
        assert!(!svg.contains(" href="));
        assert!(graphml.contains("<graphml"));
        assert!(graphml.contains("<node id=\"stable\""));
        assert!(graphml
            .contains("<edge id=\"stable-progressed\" source=\"stable\" target=\"progressed\""));
        assert!(graphml.contains("<data key=\"absorbing\">true</data>"));
    }

    #[test]
    fn layout_requires_every_state_exactly_once_and_bounded_coordinates() {
        let mut missing = positions();
        missing.pop();
        assert!(render_diagram(&model_raw(), &missing)
            .unwrap_err()
            .contains("every state"));

        let mut duplicate = positions();
        duplicate[2].state_id = "stable".into();
        assert!(render_diagram(&model_raw(), &duplicate)
            .unwrap_err()
            .contains("unique"));

        let mut outside = positions();
        outside[0].x = -1;
        assert!(render_diagram(&model_raw(), &outside)
            .unwrap_err()
            .contains("coordinates"));
    }

    #[test]
    fn generation_is_source_current_and_never_overwrites_an_external_edit() {
        let keep_fixture = std::env::var_os("AI4HEOR_KEEP_CONCEPTUAL_DIAGRAM_FIXTURE")
            .map(std::path::PathBuf::from);
        let root = keep_fixture.clone().unwrap_or_else(|| {
            std::env::temp_dir().join(format!("ai4heor-conceptual-diagram-{}", std::process::id()))
        });
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        std::fs::write(root.join(MODEL_PATH), model_raw()).unwrap();

        let before = audit_at(&root);
        assert!(before.ready_to_generate);
        assert!(!before.outputs_current);
        let generated = generate_at(&root, positions()).unwrap();
        assert!(generated.outputs_current);
        assert_eq!(generated.positions, positions());

        if keep_fixture.is_some() {
            return;
        }

        let svg_path = root.join(SVG_PATH);
        std::fs::write(&svg_path, b"external edit").unwrap();
        let changed = audit_at(&root);
        assert!(!changed.outputs_current);
        let error = generate_at(&root, positions()).unwrap_err();
        assert!(error.contains("changed outside AI4HEOR"));
        assert_eq!(std::fs::read(svg_path).unwrap(), b"external edit");

        if keep_fixture.is_none() {
            let _ = std::fs::remove_dir_all(root);
        }
    }
}
