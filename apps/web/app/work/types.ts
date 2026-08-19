export type ChangeEvent = {
  id: string;
  target_type: string;
  target_id: string;
  event_type: string;
  field_name: string | null;
  old_value: unknown;
  new_value: unknown;
  detected_at: string;
  severity: "info" | "warning" | "critical";
  old_observation_id: string | null;
  new_observation_id: string | null;
};

export type Action = {
  id: string;
  change_event_id: string;
  title: string;
  reason: string | null;
  owner_user_id: string | null;
  due_at: string | null;
  status: "open" | "in_progress" | "done" | "dismissed";
  outcome_note: string | null;
  created_at: string;
  closed_at: string | null;
};

export type ActionDetail = Action & {
  history: Array<{
    id: string;
    from_status: string | null;
    to_status: string;
    changed_by: string | null;
    changed_at: string;
    note: string | null;
  }>;
};

export type Page<T> = { items: T[]; next_cursor: string | null };

