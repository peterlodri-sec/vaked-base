//! Parse GOALS.md phases (for milestone-sync mode without an LLM).

use crate::output::MilestoneSpec;

pub(crate) fn parse_goals_phases(goals_md: &str) -> Vec<MilestoneSpec> {
    let mut milestones = Vec::new();
    let mut current_title: Option<String> = None;
    let mut bullets: Vec<String> = Vec::new();

    for line in goals_md.lines() {
        if let Some(rest) = line.strip_prefix("### Phase ") {
            // Flush the previous phase before starting the new one.
            if let Some(title) = current_title.take() {
                let desc = bullets.iter().take(3).cloned().collect::<Vec<_>>().join("\n");
                milestones.push(MilestoneSpec { title, description: desc });
                bullets.clear();
            }
            // rest = "0 — Language foundation *(in progress)*"
            // Strip the *(status)* annotation and prepend "Phase " back so the
            // title matches the exact phase heading text from GOALS.md.
            let clean = rest.trim().split(" *(").next().unwrap_or(rest.trim()).trim();
            current_title = Some(format!("Phase {clean}"));
        } else if line.starts_with("- [") && current_title.is_some() {
            bullets.push(line.trim().to_string());
        }
    }
    // Flush the last phase.
    if let Some(title) = current_title {
        let desc = bullets.iter().take(3).cloned().collect::<Vec<_>>().join("\n");
        milestones.push(MilestoneSpec { title, description: desc });
    }
    milestones
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_goals_phases_extracts_all_six() {
        let goals = r#"
### Phase 0 — Language foundation *(in progress)*
- [x] EBNF grammar
- [ ] Full lowering

### Phase 1 — Compiler maturity
- [ ] vakedc check
- [ ] LSP server

### Phase 2 — Runtime: stubs → real
- [ ] OTP plane

### Phase 3 — Wire protocol
- [ ] HCP RFCs

### Phase 4 — Surfaces and observability
- [ ] Operator surface

### Phase 5 — Language v1
- [ ] Grammar stable
"#;
        let phases = parse_goals_phases(goals);
        assert_eq!(phases.len(), 6);
        assert!(phases[0].title.contains("Language foundation") || phases[0].title.contains("0"));
        assert!(phases[5].title.contains("Language v1") || phases[5].title.contains("5"));
    }
}
