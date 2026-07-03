"use client";

import { useState } from "react";

import type { TeamMember, TeamRole } from "@/lib/team";

interface Props {
  member: TeamMember;
  isSelf: boolean;
  isOwner: boolean;
  onChangeRole: (role: TeamRole) => Promise<void>;
  onRemove: () => Promise<void>;
}

export function MemberRow({
  member,
  isSelf,
  isOwner,
  onChangeRole,
  onRemove,
}: Props) {
  const [saving, setSaving] = useState(false);
  const disabled = !isOwner || isSelf || saving;

  return (
    <li className="flex items-center justify-between rounded border p-3">
      <div>
        <p className="font-medium">
          {member.full_name} {isSelf ? "(you)" : ""}
        </p>
        <p className="text-xs text-muted-foreground">{member.email}</p>
      </div>
      <div className="flex items-center gap-2">
        <select
          aria-label="Role"
          value={member.role}
          onChange={async (e) => {
            setSaving(true);
            try {
              await onChangeRole(e.target.value as TeamRole);
            } finally {
              setSaving(false);
            }
          }}
          disabled={disabled}
          className="rounded border px-2 py-1 text-sm disabled:opacity-50"
        >
          <option value="agent">Agent</option>
          <option value="admin">Admin</option>
          <option value="owner">Owner</option>
        </select>
        {!isSelf ? (
          <button
            type="button"
            aria-label="Remove member"
            onClick={onRemove}
            disabled={disabled}
            className="rounded border border-red-300 px-3 py-1 text-sm text-red-600 disabled:opacity-50"
          >
            Remove
          </button>
        ) : null}
      </div>
    </li>
  );
}
