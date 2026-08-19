import { getAllPages, request } from "@novel-signal/api-client";
import type { Action, ActionDetail, ChangeEvent, Page } from "./types";

export const loadChanges = (eventType?: string) =>
  getAllPages<ChangeEvent>(eventType ? `/changes?event_type=${encodeURIComponent(eventType)}` : "/changes");

export const loadActions = (status?: Action["status"]) =>
  getAllPages<Action>(status ? `/actions?status=${status}` : "/actions");

export const loadChange = (id: string) => request<ChangeEvent>(`/changes/${id}`);
export const loadAction = (id: string) => request<ActionDetail>(`/actions/${id}`);

export function createAction(change: ChangeEvent, input: { title: string; reason?: string; owner_user_id?: string; due_at?: string }) {
  return request<Action>(`/changes/${change.id}/actions`, {
    method: "POST",
    body: { change_event_id: change.id, ...input },
  });
}

export function transitionAction(id: string, status: Action["status"], note?: string) {
  return request<Action>(`/actions/${id}/transition`, {
    method: "POST",
    body: { status, note },
  });
}

export type OperationsModule = { module: string; owner: string; status: string };
export const loadOperations = () => request<OperationsModule>("/collection/meta");

