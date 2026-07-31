mod resource_staging;

fn main() {
    let out_dir = std::env::var_os("OUT_DIR")
        .map(std::path::PathBuf::from)
        .expect("Cargo did not provide OUT_DIR");
    println!("cargo:rerun-if-changed=resource-staging.trigger");
    resource_staging::clean_staged_admitted_skills(&out_dir)
        .expect("cannot clean admitted Skill staging directory");
    tauri_build::build()
}
