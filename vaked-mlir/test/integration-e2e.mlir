// E2E Integration Test: Full pipeline (Pass 1 → Pass 2 → Pass 3)
// Tests minimal 3-agent topology: source → process → sink

module {
  vaked.agent @source {
    %h = vaked.execute_step() -> !vaked.state_hash
    vaked.yield %h
  }

  vaked.agent @process {
    %from_source = vaked.consume @source : !vaked.state_hash
    %h = vaked.execute_with_dep(%from_source) -> !vaked.state_hash
    vaked.yield %h
  }

  vaked.agent @sink {
    %from_process = vaked.consume @process : !vaked.state_hash
    %h = vaked.execute_with_dep(%from_process) -> !vaked.state_hash
    vaked.yield %h
  }
}
