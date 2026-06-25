//! Shared state — bọc trong Arc<RwLock<>>. Dùng tokio::sync::RwLock (fix lỗi #4:
//! std::sync::RwLock giữ qua .await sẽ deadlock).

use crate::roles::AgentManifest;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Trạng thái toàn hệ thống — nhiều agent đọc song song, chỉ Orchestrator ghi.
#[derive(Debug, Default)]
pub struct SystemState {
    /// Danh sách agent đã đăng ký, key = agent_id.
    pub agents: HashMap<String, AgentManifest>,
    /// Số task đã hoàn thành.
    pub tasks_completed: u64,
    /// Số task lỗi.
    pub tasks_failed: u64,
}

impl SystemState {
    pub fn register(&mut self, manifest: AgentManifest) {
        self.agents.insert(manifest.id.clone(), manifest);
    }

    pub fn agent_count(&self) -> usize {
        self.agents.len()
    }
}

/// Handle chia sẻ an toàn giữa các luồng.
pub type SharedState = Arc<RwLock<SystemState>>;

pub fn new_shared_state() -> SharedState {
    Arc::new(RwLock::new(SystemState::default()))
}
