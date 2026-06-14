//! Disk guard: free-space probe + scratch usage accounting + admit decision.

use std::path::Path;

#[derive(Debug, Clone, Copy)]
pub struct Guard {
    pub min_free_bytes: u64,
    pub scratch_cap_bytes: u64,
}

impl Guard {
    /// Admit a new task only if free space is above the floor AND scratch usage is
    /// under the cap. The orchestrator pauses intake when this returns false.
    pub fn admits(&self, free_bytes: u64, scratch_used_bytes: u64) -> bool {
        free_bytes >= self.min_free_bytes && scratch_used_bytes < self.scratch_cap_bytes
    }
}

/// Recursively sum regular-file sizes under `root` (best-effort).
pub fn dir_size_bytes(root: &Path) -> u64 {
    fn walk(p: &Path, acc: &mut u64) {
        let Ok(rd) = std::fs::read_dir(p) else {
            return;
        };
        for e in rd.flatten() {
            match e.file_type() {
                Ok(ft) if ft.is_dir() => walk(&e.path(), acc),
                Ok(ft) if ft.is_file() => {
                    if let Ok(m) = e.metadata() {
                        *acc += m.len();
                    }
                }
                _ => {}
            }
        }
    }
    let mut acc = 0;
    walk(root, &mut acc);
    acc
}

/// Free bytes on the filesystem containing `path`, via `df -kP` (portable).
pub fn free_bytes(path: &Path) -> std::io::Result<u64> {
    let out = std::process::Command::new("df")
        .arg("-kP")
        .arg(path)
        .output()?;
    let s = String::from_utf8_lossy(&out.stdout);
    // Row 2, column 4 (Available) is in 1K blocks under POSIX `-P`.
    let avail_k: u64 = s
        .lines()
        .nth(1)
        .and_then(|l| l.split_whitespace().nth(3))
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    Ok(avail_k * 1024)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guard_pauses_below_floor_or_over_cap() {
        let g = Guard {
            min_free_bytes: 10,
            scratch_cap_bytes: 100,
        };
        assert!(!g.admits(5, 0), "free below floor -> pause");
        assert!(!g.admits(50, 100), "scratch at cap -> pause");
        assert!(g.admits(50, 40), "both ok -> admit");
        assert!(g.admits(10, 99), "exactly at floor, under cap -> admit");
    }

    #[test]
    fn dir_size_counts_files() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("a"), vec![0u8; 1234]).unwrap();
        std::fs::create_dir(d.path().join("sub")).unwrap();
        std::fs::write(d.path().join("sub/b"), vec![0u8; 66]).unwrap();
        assert_eq!(dir_size_bytes(d.path()), 1300);
    }

    #[test]
    fn free_bytes_on_tmp_is_positive() {
        let d = tempfile::tempdir().unwrap();
        assert!(free_bytes(d.path()).unwrap() > 0);
    }
}
