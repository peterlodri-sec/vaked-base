//! Eval harness: score the reviewer against local *.diff/*.expect fixtures
//! (adk-eval ResponseScorer + BaselineStore regression gating).

use std::collections::HashMap;

use adk_rust::eval::criteria::{ResponseMatchConfig, SimilarityAlgorithm};
use adk_rust::eval::{BaselineStore, ResponseScorer};
use anyhow::{Context, Result, anyhow};

use crate::agent::{ask, build_runner_with};
use crate::config::{Config, env_first, truncate};
use crate::github::PrMeta;
use crate::prompts::{build_prompt, language_addenda, system_prompt};
use crate::render::render_review;

pub(crate) fn eval_dir() -> Option<String> {
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        if a == "--eval" {
            return args.next();
        }
    }
    None
}

pub(crate) async fn run_eval(dir: &str) -> Result<()> {
    let api_key = env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"])
        .ok_or_else(|| anyhow!("eval needs OPENROUTER_API_KEY"))?;
    let cfg = Config::eval_defaults();
    let runner = build_runner_with(
        &cfg,
        &api_key,
        &cfg.reasoning_effort,
        4096,
        cfg.structured,
        None,
        system_prompt(cfg.max_findings, cfg.crabcc_budget, cfg.structured),
    )?;

    let mut entries: Vec<_> = std::fs::read_dir(dir)
        .with_context(|| format!("reading eval dir {dir}"))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "diff"))
        .collect();
    entries.sort();
    if entries.is_empty() {
        return Err(anyhow!("no *.diff fixtures in {dir}"));
    }

    // adk-eval ResponseScorer (Contains) replaces the hand-rolled `contains`.
    let scorer = ResponseScorer::with_config(ResponseMatchConfig {
        algorithm: SimilarityAlgorithm::Contains,
        ignore_case: true,
        ..Default::default()
    });

    // metric_name -> case_id -> score, for adk-eval's BaselineStore.
    let mut scores: HashMap<String, f64> = HashMap::new();
    let (mut pass, mut total) = (0usize, 0usize);
    for diff_path in entries {
        let name = diff_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned();
        let diff = std::fs::read_to_string(&diff_path)?;
        let expects: Vec<String> = std::fs::read_to_string(diff_path.with_extension("expect"))
            .unwrap_or_default()
            .lines()
            .map(|l| l.trim().to_string())
            .filter(|l| !l.is_empty())
            .collect();

        let meta = PrMeta {
            number: 0,
            title: name.clone(),
            body: String::new(),
            files: vec![format!("{name}.rs")],
            labels: vec![],
        };
        let (body, truncated) = truncate(&diff, cfg.max_diff_chars);
        let prompt = build_prompt(&meta, &body, truncated, &language_addenda(&meta.files));
        let (raw, _) = ask(&runner, prompt).await?;
        let (review, _, _) = render_review(&raw, cfg.max_findings as usize);
        let (score, hits) = substring_score(&scorer, &review, &expects);
        let ok = hits == expects.len();
        total += 1;
        if ok {
            pass += 1;
        }
        scores.insert(name.clone(), score);
        println!(
            "[{}] {name}: {hits}/{} expected substrings (score {score:.2})",
            if ok { "PASS" } else { "FAIL" },
            expects.len()
        );
    }

    // Regression gating (adk-eval BaselineStore). A regression is
    // baseline - current > tolerance on any case; the baseline ratchets up only on
    // a fully-passing, non-regressing run so it is never lowered silently.
    let metrics: HashMap<String, HashMap<String, f64>> =
        HashMap::from([("response_match".to_string(), scores)]);
    let tolerance = std::env::var("PR_REVIEW_EVAL_TOLERANCE")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0.0);
    let store = BaselineStore::new(format!("{dir}/.baseline.json"));
    let regressions = store
        .check_regressions(&metrics, tolerance)
        .map_err(|e| anyhow!("baseline check: {e}"))?;
    for r in &regressions {
        println!(
            "REGRESSION {} [{}]: {:.2} -> {:.2} (Δ{:.2})",
            r.metric_name, r.case_id, r.baseline_value, r.current_value, r.delta
        );
    }
    println!(
        "\neval: {pass}/{total} fixtures passed; {} regression(s)",
        regressions.len()
    );

    if !regressions.is_empty() {
        return Err(anyhow!("{} regression(s) vs baseline", regressions.len()));
    }
    if pass == total {
        store
            .save("vaked-pr-review", &metrics)
            .map_err(|e| anyhow!("baseline save: {e}"))?;
        Ok(())
    } else {
        Err(anyhow!("{}/{total} fixtures failed", total - pass))
    }
}

/// Fraction of `expects` substrings present in `review`, scored via adk-eval's
/// `ResponseScorer` (Contains ⇒ 1.0 when present, else 0.0). Returns
/// (mean_score, hits). Empty expectations score a clean 1.0.
pub(crate) fn substring_score(scorer: &ResponseScorer, review: &str, expects: &[String]) -> (f64, usize) {
    if expects.is_empty() {
        return (1.0, 0);
    }
    let per: Vec<f64> = expects.iter().map(|e| scorer.score(e, review)).collect();
    let hits = per.iter().filter(|s| **s >= 1.0).count();
    let mean = per.iter().sum::<f64>() / per.len() as f64;
    (mean, hits)
}

#[cfg(test)]
mod eval_tests {
    use super::*;

    #[test]
    fn substring_score_counts_present_expectations() {
        let scorer = ResponseScorer::with_config(ResponseMatchConfig {
            algorithm: SimilarityAlgorithm::Contains,
            ignore_case: true,
            ..Default::default()
        });
        let review = "**Verdict:** issues\n### Major\n- `a.rs:1` — unwrap on a None path; use `?`";
        let expects = vec!["unwrap".to_string(), "deadlock".to_string()];
        let (mean, hits) = substring_score(&scorer, review, &expects);
        assert_eq!(hits, 1); // "unwrap" present, "deadlock" absent
        assert!((mean - 0.5).abs() < 1e-9);
        // Case-insensitive containment holds.
        assert_eq!(substring_score(&scorer, review, &["VERDICT".to_string()]).1, 1);
    }
}
