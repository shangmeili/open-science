// Content-free model-call audit ledger. The desktop persists only runtime,
// provider/model identifiers, timing, usage, and runtime-reported cost — never
// prompt or response text — in a tamper-evident workspace JSONL file.
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::Path;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::AppHandle;

use crate::runtime::workspace_dir;

const STORE_DIR: &str = ".openscience";
const STORE_FILE: &str = "model-calls.jsonl";
const SCHEMA_VERSION: u32 = 1;
const MAX_STORE_BYTES: u64 = 20 * 1024 * 1024;
const MAX_ID_LEN: usize = 256;
const MAX_FINISH_LEN: usize = 128;

#[derive(Default)]
pub struct ModelCallState(pub Mutex<()>);

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCallTokens {
    pub input: u64,
    pub output: u64,
    pub reasoning: u64,
    pub cache_read: u64,
    pub cache_write: u64,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCallInput {
    pub runtime: String,
    pub runtime_version: String,
    pub session_id: String,
    pub message_id: String,
    pub parent_message_id: String,
    pub provider_id: String,
    pub model_id: String,
    pub agent: String,
    pub created_at: u64,
    pub completed_at: u64,
    pub runtime_reported_cost: f64,
    pub tokens: ModelCallTokens,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub finish: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prompt_template_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prompt_template_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub response_language: Option<String>,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCallRecord {
    pub schema_version: u32,
    pub call_id: String,
    pub recorded_at: u64,
    #[serde(flatten)]
    pub input: ModelCallInput,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_event_hash: Option<String>,
    pub event_hash: String,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ModelCallHashPayload<'a> {
    schema_version: u32,
    call_id: &'a str,
    recorded_at: u64,
    input: &'a ModelCallInput,
    previous_event_hash: &'a Option<String>,
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn call_id(message_id: &str) -> String {
    format!("call_{}", &sha256_hex(message_id.as_bytes())[..16])
}

fn valid_required(value: &str, max_len: usize) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty() && trimmed.len() <= max_len && !trimmed.chars().any(char::is_control)
}

fn validate_input(input: &ModelCallInput) -> Result<(), String> {
    for (label, value) in [
        ("runtime", input.runtime.as_str()),
        ("runtimeVersion", input.runtime_version.as_str()),
        ("sessionId", input.session_id.as_str()),
        ("messageId", input.message_id.as_str()),
        ("parentMessageId", input.parent_message_id.as_str()),
        ("providerId", input.provider_id.as_str()),
        ("modelId", input.model_id.as_str()),
        ("agent", input.agent.as_str()),
    ] {
        if !valid_required(value, MAX_ID_LEN) {
            return Err(format!("invalid model-call {label}"));
        }
    }
    if input.completed_at < input.created_at {
        return Err("invalid model-call timing".into());
    }
    if !input.runtime_reported_cost.is_finite() || input.runtime_reported_cost < 0.0 {
        return Err("invalid runtime-reported model-call cost".into());
    }
    if let Some(finish) = &input.finish {
        if !valid_required(finish, MAX_FINISH_LEN) {
            return Err("invalid model-call finish reason".into());
        }
    }
    match (
        &input.prompt_template_id,
        &input.prompt_template_sha256,
        &input.response_language,
    ) {
        (None, None, None) => {}
        (Some(id), Some(hash), Some(language))
            if valid_required(id, MAX_ID_LEN)
                && id.chars().all(|ch| {
                    ch.is_ascii_alphanumeric() || matches!(ch, '/' | '-' | '_' | '.')
                })
                && hash.len() == 64
                && hash
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
                && valid_required(language, 64) => {}
        _ => return Err("invalid or incomplete model-call prompt template context".into()),
    }
    Ok(())
}

fn store_path(root: &Path, create: bool) -> Result<std::path::PathBuf, String> {
    let dir = root.join(STORE_DIR);
    match std::fs::symlink_metadata(&dir) {
        Ok(meta) if meta.file_type().is_symlink() => {
            return Err("model-call store directory must not be a symlink".into())
        }
        Ok(meta) if !meta.is_dir() => return Err("model-call store path is not a directory".into()),
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && create => {
            std::fs::create_dir_all(&dir)
                .map_err(|e| format!("model-call store directory failed: {e}"))?;
            let meta = std::fs::symlink_metadata(&dir)
                .map_err(|e| format!("model-call store directory unavailable: {e}"))?;
            if meta.file_type().is_symlink() || !meta.is_dir() {
                return Err("model-call store directory is unsafe".into());
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(format!("model-call store directory unavailable: {error}")),
    }
    Ok(dir.join(STORE_FILE))
}

fn verify_regular_file(path: &Path) -> Result<Option<std::fs::Metadata>, String> {
    match std::fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_symlink() => {
            Err("model-call ledger must not be a symlink".into())
        }
        Ok(meta) if !meta.is_file() => Err("model-call ledger is not a regular file".into()),
        Ok(meta) if meta.len() > MAX_STORE_BYTES => Err("model-call ledger is too large".into()),
        Ok(meta) => Ok(Some(meta)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("model-call ledger unavailable: {error}")),
    }
}

fn record_event_hash(record: &ModelCallRecord) -> Result<String, String> {
    let payload = ModelCallHashPayload {
        schema_version: record.schema_version,
        call_id: &record.call_id,
        recorded_at: record.recorded_at,
        input: &record.input,
        previous_event_hash: &record.previous_event_hash,
    };
    let bytes = serde_json::to_vec(&payload)
        .map_err(|e| format!("model-call hash serialization failed: {e}"))?;
    Ok(sha256_hex(&bytes))
}

fn read_records(root: &Path) -> Result<Vec<ModelCallRecord>, String> {
    let path = store_path(root, false)?;
    if verify_regular_file(&path)?.is_none() {
        return Ok(Vec::new());
    }
    let text =
        std::fs::read_to_string(&path).map_err(|e| format!("model-call ledger unreadable: {e}"))?;
    let mut records = Vec::new();
    let mut previous: Option<String> = None;
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            return Err(format!("model-call ledger line {} is empty", index + 1));
        }
        let record: ModelCallRecord = serde_json::from_str(line)
            .map_err(|e| format!("model-call ledger line {} is invalid: {e}", index + 1))?;
        validate_input(&record.input)?;
        if record.schema_version != SCHEMA_VERSION
            || record.call_id != call_id(&record.input.message_id)
            || record.previous_event_hash != previous
            || record.event_hash != record_event_hash(&record)?
        {
            return Err(format!(
                "model-call ledger integrity check failed at line {}",
                index + 1
            ));
        }
        previous = Some(record.event_hash.clone());
        records.push(record);
    }
    Ok(records)
}

fn append_records(root: &Path, records: &[ModelCallRecord]) -> Result<(), String> {
    if records.is_empty() {
        return Ok(());
    }
    let path = store_path(root, true)?;
    verify_regular_file(&path)?;
    let serialized = records
        .iter()
        .map(serde_json::to_string)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| format!("model-call serialization failed: {e}"))?
        .join("\n")
        + "\n";
    let existing_bytes = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
    if existing_bytes + serialized.len() as u64 > MAX_STORE_BYTES {
        return Err("model-call ledger would exceed its size limit".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| format!("model-call ledger append failed: {e}"))?;
    file.write_all(serialized.as_bytes())
        .and_then(|_| file.sync_data())
        .map_err(|e| format!("model-call ledger flush failed: {e}"))
}

fn record_model_calls_inner(
    root: &Path,
    inputs: Vec<ModelCallInput>,
) -> Result<Vec<ModelCallRecord>, String> {
    let mut ledger = read_records(root)?;
    let mut appended = Vec::new();
    let mut results = Vec::with_capacity(inputs.len());
    for input in inputs {
        validate_input(&input)?;
        if let Some(existing) = ledger
            .iter()
            .find(|record| record.input.message_id == input.message_id)
        {
            let mut existing_core = existing.input.clone();
            existing_core.prompt_template_id = None;
            existing_core.prompt_template_sha256 = None;
            existing_core.response_language = None;
            let mut incoming_core = input.clone();
            incoming_core.prompt_template_id = None;
            incoming_core.prompt_template_sha256 = None;
            incoming_core.response_language = None;
            let existing_has_context = existing.input.prompt_template_id.is_some();
            let incoming_has_context = input.prompt_template_id.is_some();
            if existing.input == input
                || (existing_core == incoming_core
                    && (!existing_has_context || !incoming_has_context))
            {
                results.push(existing.clone());
                continue;
            }
            return Err("conflicting model-call record for messageId".into());
        }
        let next_call_id = call_id(&input.message_id);
        if ledger.iter().any(|record| record.call_id == next_call_id) {
            return Err("conflicting model-call callId".into());
        }
        let mut record = ModelCallRecord {
            schema_version: SCHEMA_VERSION,
            call_id: next_call_id,
            recorded_at: now_ms(),
            input,
            previous_event_hash: ledger.last().map(|record| record.event_hash.clone()),
            event_hash: String::new(),
        };
        record.event_hash = record_event_hash(&record)?;
        ledger.push(record.clone());
        appended.push(record.clone());
        results.push(record);
    }
    append_records(root, &appended)?;
    Ok(results)
}

fn record_model_call_inner(root: &Path, input: ModelCallInput) -> Result<ModelCallRecord, String> {
    record_model_calls_inner(root, vec![input])?
        .into_iter()
        .next()
        .ok_or_else(|| "model-call input is missing".into())
}

fn list_model_calls_inner(root: &Path) -> Result<Vec<ModelCallRecord>, String> {
    read_records(root)
}

#[tauri::command(async)]
pub fn record_model_call(
    app: AppHandle,
    state: tauri::State<ModelCallState>,
    input: ModelCallInput,
) -> Result<ModelCallRecord, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "model-call ledger lock poisoned")?;
    record_model_call_inner(&workspace_dir(&app)?, input)
}

#[tauri::command(async)]
pub fn record_model_calls(
    app: AppHandle,
    state: tauri::State<ModelCallState>,
    inputs: Vec<ModelCallInput>,
) -> Result<Vec<ModelCallRecord>, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "model-call ledger lock poisoned")?;
    record_model_calls_inner(&workspace_dir(&app)?, inputs)
}

#[tauri::command(async)]
pub fn list_model_calls(
    app: AppHandle,
    state: tauri::State<ModelCallState>,
) -> Result<Vec<ModelCallRecord>, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "model-call ledger lock poisoned")?;
    list_model_calls_inner(&workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn temp_root(tag: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("ai4heor-model-calls-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn input(message_id: &str) -> ModelCallInput {
        ModelCallInput {
            runtime: "opencode".into(),
            runtime_version: "1.17.13".into(),
            session_id: "ses_1".into(),
            message_id: message_id.into(),
            parent_message_id: "msg_user_1".into(),
            provider_id: "mock-provider".into(),
            model_id: "mock-model".into(),
            agent: "build".into(),
            created_at: 1_000,
            completed_at: 1_250,
            runtime_reported_cost: 0.0123,
            tokens: ModelCallTokens {
                input: 120,
                output: 45,
                reasoning: 8,
                cache_read: 30,
                cache_write: 4,
            },
            finish: Some("stop".into()),
            prompt_template_id: None,
            prompt_template_sha256: None,
            response_language: None,
        }
    }

    #[test]
    fn records_content_free_hash_chained_and_idempotent_calls() {
        let root = temp_root("record");
        let first = record_model_call_inner(&root, input("msg_assistant_1")).unwrap();
        let duplicate = record_model_call_inner(&root, input("msg_assistant_1")).unwrap();
        assert_eq!(first, duplicate);
        assert_eq!(first.schema_version, 1);
        assert!(first.call_id.starts_with("call_"));
        assert_eq!(first.previous_event_hash, None);

        let replay = record_model_calls_inner(
            &root,
            vec![input("msg_assistant_1"), input("msg_assistant_2")],
        )
        .unwrap();
        assert_eq!(replay[0], first);
        let second = replay[1].clone();
        assert_eq!(
            second.previous_event_hash.as_deref(),
            Some(first.event_hash.as_str())
        );

        let file = root.join(".openscience/model-calls.jsonl");
        let text = std::fs::read_to_string(&file).unwrap();
        assert_eq!(text.lines().count(), 2);
        for forbidden in ["prompt", "response", "apiKey", "requestUrl", "error"] {
            assert!(
                !text.contains(forbidden),
                "ledger leaked forbidden field {forbidden}"
            );
        }
        assert_eq!(list_model_calls_inner(&root).unwrap(), vec![first, second]);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_conflicts_invalid_values_and_corrupt_history() {
        let root = temp_root("invalid");
        record_model_call_inner(&root, input("msg_assistant_1")).unwrap();

        let mut conflict = input("msg_assistant_1");
        conflict.tokens.output += 1;
        assert!(record_model_call_inner(&root, conflict).is_err());

        let mut invalid_time = input("msg_assistant_time");
        invalid_time.completed_at = invalid_time.created_at - 1;
        assert!(record_model_call_inner(&root, invalid_time).is_err());

        let mut invalid_cost = input("msg_assistant_cost");
        invalid_cost.runtime_reported_cost = f64::NAN;
        assert!(record_model_call_inner(&root, invalid_cost).is_err());

        let mut partial_context = input("msg_assistant_partial_context");
        partial_context.prompt_template_id = Some("ai4heor/heor-workbench-preamble".into());
        assert!(record_model_call_inner(&root, partial_context).is_err());

        let mut invalid_hash = input("msg_assistant_invalid_hash");
        invalid_hash.prompt_template_id = Some("ai4heor/heor-workbench-preamble".into());
        invalid_hash.prompt_template_sha256 = Some("A".repeat(64));
        invalid_hash.response_language = Some("Simplified Chinese".into());
        assert!(record_model_call_inner(&root, invalid_hash).is_err());

        let file = root.join(".openscience/model-calls.jsonl");
        std::fs::write(&file, "{not-json}\n").unwrap();
        assert!(list_model_calls_inner(&root).is_err());
        assert!(record_model_call_inner(&root, input("msg_assistant_2")).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn accepts_a_bounded_prompt_template_fingerprint_without_prompt_content() {
        let mut value = serde_json::to_value(input("msg_prompt_context")).unwrap();
        let object = value.as_object_mut().unwrap();
        object.insert(
            "promptTemplateId".into(),
            serde_json::Value::String("ai4heor/heor-workbench-preamble".into()),
        );
        object.insert(
            "promptTemplateSha256".into(),
            serde_json::Value::String("a".repeat(64)),
        );
        object.insert(
            "responseLanguage".into(),
            serde_json::Value::String("Simplified Chinese".into()),
        );
        assert!(serde_json::from_value::<ModelCallInput>(value).is_ok());

        // A record written by the immediately preceding schema remains
        // idempotent when history replay now knows optional template context;
        // the append-only ledger is never rewritten in place.
        let root = temp_root("prompt-context-compat");
        let existing = record_model_call_inner(&root, input("msg_legacy")).unwrap();
        let mut enriched = input("msg_legacy");
        enriched.prompt_template_id = Some("ai4heor/heor-workbench-preamble".into());
        enriched.prompt_template_sha256 = Some("a".repeat(64));
        enriched.response_language = Some("Simplified Chinese".into());
        assert_eq!(record_model_call_inner(&root, enriched).unwrap(), existing);
        assert_eq!(list_model_calls_inner(&root).unwrap(), vec![existing]);
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn rejects_a_symlinked_ledger_file() {
        use std::os::unix::fs::symlink;

        let root = temp_root("symlink");
        let store = root.join(".openscience");
        std::fs::create_dir_all(&store).unwrap();
        let target = root.join("outside.jsonl");
        std::fs::write(&target, "").unwrap();
        symlink(&target, store.join("model-calls.jsonl")).unwrap();
        assert!(record_model_call_inner(&root, input("msg_assistant_1")).is_err());
        assert!(list_model_calls_inner(&root).is_err());
        let _ = std::fs::remove_dir_all(root);
    }
}
