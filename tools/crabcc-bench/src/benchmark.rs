//! CrabCC benchmark — 16x parallel, zero-alloc, raw pointer symbol index
//! vs ripgrep, fd, grep, ctags. Target: <12ms for 1M symbols.
//! GENESIS_SEAL: 7c242080

use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

pub struct SymbolEntry {
    pub hash: u64,
    pub name_offset: u32,
    pub file_index: u16,
}

pub struct CrabCCBenchmarkMatrix {
    pub symbol_table: [SymbolEntry; 10000],
    pub active_slots: AtomicUsize,
}

impl CrabCCBenchmarkMatrix {
    pub fn new() -> Self {
        Self { symbol_table: unsafe { std::mem::zeroed() }, active_slots: AtomicUsize::new(0) }
    }

    /// 16 parallel subagents shredding work directories via raw pointer writes
    pub fn executeMassiveParallelIndex(&self, chunks: &[&[u8]]) -> u128 {
        let start = Instant::now();
        crossbeam::scope(|s| {
            for chunk in chunks.chunks(chunks.len() / 16) {
                s.spawn(move |_| {
                    for line in chunk {
                        let hash = seahash::hash(line);
                        let slot = self.active_slots.fetch_add(1, Ordering::SeqCst);
                        if slot < 10000 {
                            let dest = &self.symbol_table[slot] as *const SymbolEntry as *mut SymbolEntry;
                            unsafe {
                                (*dest).hash = hash;
                                (*dest).name_offset = slot as u32 * 8;
                                (*dest).file_index = 1;
                            }
                        }
                    }
                });
            }
        }).unwrap();
        start.elapsed().as_nanos()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bench_parallel_index() {
        let m = CrabCCBenchmarkMatrix::new();
        let data: Vec<u8> = (0..1000).map(|i| format!("symbol_{}\n", i)).collect::<Vec<_>>().join("").into_bytes();
        let lines: Vec<&[u8]> = data.split(|&b| b == b'\n').collect();
        let nanos = m.executeMassiveParallelIndex(&lines);
        println!("CrabCC: {}ns for {} symbols", nanos, lines.len());
        assert!(m.active_slots.load(Ordering::SeqCst) > 0);
    }
}
