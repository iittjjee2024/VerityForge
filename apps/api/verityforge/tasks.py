"""Task manager + REST router: runs agent tasks in worker threads; approvals block until decided via HTTP."""
from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .agent import AgentTask, CodingAgent, Limits, State
from .gateway import ModelGateway
from .security import ApprovalGate, ApprovalRequest, Scope, SecurityContext

TERMINAL = {State.COMPLETED, State.FAILED, State.CANCELLED}


class _Pending:
    def __init__(self, req: ApprovalRequest, task_id: str):
        self.req, self.task_id = req, task_id
        self.event, self.decision = threading.Event(), None


class TaskManager:
    def __init__(self, gateway: ModelGateway, runner_factory: Callable[[SecurityContext], Callable],
                 limits: Limits | None = None, approval_timeout_s: float = 3600.0):
        self.gateway, self.runner_factory = gateway, runner_factory
        self.limits, self.timeout = limits or Limits(), approval_timeout_s
        self.gate = ApprovalGate()
        self.tasks: dict[str, AgentTask] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.pending: dict[str, _Pending] = {}
        self.lock = threading.Lock()

    def create(self, objective: str, ctx: SecurityContext, optimized: bool = True) -> AgentTask:
        task = AgentTask(objective, ctx)
        self.tasks[task.id] = task

        def approver(req: ApprovalRequest):
            p = _Pending(req, task.id)
            with self.lock:
                self.pending[req.id] = p
            p.event.wait(self.timeout)  # timeout counts as rejection (fail safe)
            return bool(p.decision) and not task.cancelled

        agent = CodingAgent(self.gateway, self.gate, self.runner_factory(ctx), approver, self.limits, optimized)
        th = threading.Thread(target=agent.run, args=(task,), daemon=True)
        self.threads[task.id] = th
        th.start()
        return task

    def decide(self, approval_id: str, approve: bool) -> None:
        with self.lock:
            p = self.pending.get(approval_id)
            if p is None or p.event.is_set():
                raise KeyError(approval_id)
            p.decision = approve
            p.event.set()

    def cancel(self, task_id: str) -> None:
        t = self.tasks[task_id]
        t.cancelled = True
        for p in list(self.pending.values()):  # release any blocked approval as rejected
            if p.task_id == task_id and not p.event.is_set():
                p.decision = False
                p.event.set()

    def open_approvals(self, task_id: str | None = None) -> list[_Pending]:
        return [p for p in self.pending.values() if not p.event.is_set() and (task_id in (None, p.task_id))]


def view(t: AgentTask) -> dict:
    u = t.usage
    return {"id": t.id, "objective": t.objective, "state": t.state.value, "outcome": t.outcome,
            "scope": t.ctx.scope.value, "acceptance_criteria": t.acceptance_criteria, "plan": t.plan,
            "relevant_files": t.relevant_files, "diffs": t.diffs,
            "test_runs": [{"command": r["command"], "result": r["result"]} for r in t.test_runs],
            "repairs": t.repairs, "events": t.events,
            "usage": {**{k: v for k, v in asdict(u).items()}, "total_tokens": u.total_tokens,
                      "cost_is_estimate": True}}


class TaskIn(BaseModel):
    objective: str
    workspace_root: str
    confidential: bool = False
    optimized: bool = True


class DecisionIn(BaseModel):
    approve: bool


def make_router(m: TaskManager, user_dep=None) -> APIRouter:
    r = APIRouter(prefix="/api/v1")
    # user_dep resolves the authenticated user id (or "local" when auth is disabled). Injected so this
    # module stays decoupled from the auth implementation.
    from fastapi import Depends
    if user_dep is None:
        def user_dep() -> str:
            return "local"
    U = Depends(user_dep)

    @r.post("/tasks", status_code=202)
    def create_task(body: TaskIn, user: str = U):
        ctx = SecurityContext(user, body.workspace_root, Scope.CONFIDENTIAL if body.confidential else Scope.STANDARD,
                              body.workspace_root)
        return view(m.create(body.objective, ctx, body.optimized))

    @r.get("/tasks")
    def list_tasks():
        return [view(t) for t in m.tasks.values()]

    @r.get("/tasks/{task_id}")
    def get_task(task_id: str):
        if task_id not in m.tasks:
            raise HTTPException(404, "unknown task")
        return view(m.tasks[task_id])

    @r.post("/tasks/{task_id}/cancel")
    def cancel(task_id: str, user: str = U):
        if task_id not in m.tasks:
            raise HTTPException(404, "unknown task")
        m.cancel(task_id)
        return {"cancelled": True}

    @r.get("/approvals")
    def approvals(task_id: str | None = None):
        return [{"id": p.req.id, "task_id": p.task_id, "action": p.req.action.value, "target": p.req.target,
                 "detail": p.req.detail, "impact": p.req.impact, "reason": p.req.reason}
                for p in m.open_approvals(task_id)]

    @r.post("/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: DecisionIn, user: str = U):
        from .security import AUDIT
        try:
            m.decide(approval_id, body.approve)
        except KeyError:
            raise HTTPException(404, "unknown or already decided approval")
        AUDIT.record("approval_decided_by", "info", user=user, approval=approval_id,
                     decision="approved" if body.approve else "rejected")
        return {"id": approval_id, "decision": "approved" if body.approve else "rejected"}

    return r
