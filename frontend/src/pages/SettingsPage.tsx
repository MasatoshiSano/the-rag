// SettingsPage: user preferences, search settings, behavior profile
// WCAG 2.2 AA: landmark regions, skip link target, form labels, ARIA live regions

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, TextField } from "@serendie/ui";
import { getMe, updateSettings } from "../api/users";
import { useUserStore } from "../stores/userStore";
import { SearchSettings } from "../components/settings/SearchSettings";
import { ProfileInfo } from "../components/settings/ProfileInfo";

const pageStyle: React.CSSProperties = {
  maxWidth: 720,
  margin: "0 auto",
  padding: "16px",
  display: "flex",
  flexDirection: "column",
  gap: "32px",
  boxSizing: "border-box",
  width: "100%",
};

const headingStyle: React.CSSProperties = {
  margin: "0 0 24px 0",
  fontSize: "var(--sds-typography-headline-small-font-size, 24px)",
  fontWeight: 700,
  color: "var(--sds-color-on-surface-default)",
};

const sectionStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container-low)",
  borderRadius: "var(--sds-border-radius-medium, 12px)",
  padding: "24px",
  display: "flex",
  flexDirection: "column",
  gap: "16px",
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const updateUserSettings = useUserStore((s) => s.updateUserSettings);
  const storedUser = useUserStore((s) => s.user);

  const [nicknameInput, setNicknameInput] = useState<string | null>(null);
  const [nicknameSaveSuccess, setNicknameSaveSuccess] = useState(false);

  const { data: user, isLoading, isError } = useQuery({
    queryKey: ["user", "me"],
    queryFn: getMe,
    initialData: storedUser ?? undefined,
    staleTime: 30_000,
  });

  const nicknameMutation = useMutation({
    mutationFn: (nickname: string) => updateSettings({ nickname }),
    onSuccess: (updated) => {
      updateUserSettings({ nickname: updated.nickname });
      queryClient.setQueryData(["user", "me"], updated);
      setNicknameInput(null);
      setNicknameSaveSuccess(true);
      setTimeout(() => setNicknameSaveSuccess(false), 3000);
    },
  });

  function handleNicknameSave() {
    const trimmed = (nicknameInput ?? "").trim();
    if (!trimmed) return;
    nicknameMutation.mutate(trimmed);
  }

  if (isLoading) {
    return (
      <section aria-label="設定" aria-busy="true" style={pageStyle}>
        <p style={{ color: "var(--sds-color-on-surface-low)" }}>読み込み中...</p>
      </section>
    );
  }

  if (isError || !user) {
    return (
      <section aria-label="設定" style={pageStyle}>
        <p role="alert" style={{ color: "var(--sds-color-error-default)" }}>
          設定の読み込みに失敗しました。ページを再読み込みしてください。
        </p>
      </section>
    );
  }

  const currentNickname = nicknameInput !== null ? nicknameInput : user.nickname;

  return (
    <section aria-label="設定" style={pageStyle}>
      <h1 style={headingStyle}>設定</h1>

      {/* Section 1: 検索設定 */}
      <SearchSettings user={user} />

      {/* Section 2: プロフィール */}
      <section aria-labelledby="profile-section-heading" style={sectionStyle}>
        <h2
          id="profile-section-heading"
          style={{
            margin: 0,
            fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
            fontWeight: 700,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          プロフィール
        </h2>

        <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <TextField
              label="ニックネーム"
              placeholder="ニックネームを入力"
              value={currentNickname}
              onChange={(e) => setNicknameInput(e.target.value)}
            />
          </div>
          <Button
            styleType="filled"
            size="medium"
            onClick={handleNicknameSave}
            isLoading={nicknameMutation.isPending}
            disabled={
              nicknameMutation.isPending ||
              (nicknameInput ?? "").trim() === "" ||
              nicknameInput === null
            }
            aria-label="ニックネームを保存"
          >
            保存
          </Button>
        </div>

        {nicknameSaveSuccess && (
          <p
            role="status"
            aria-live="polite"
            style={{
              color: "var(--sds-color-primary-default)",
              fontSize: "var(--sds-typography-body-small-font-size, 12px)",
              margin: 0,
            }}
          >
            ニックネームを保存しました。
          </p>
        )}

        {nicknameMutation.isError && (
          <p
            role="alert"
            style={{
              color: "var(--sds-color-error-default)",
              fontSize: "var(--sds-typography-body-small-font-size, 12px)",
              margin: 0,
            }}
          >
            保存に失敗しました。再度お試しください。
          </p>
        )}
      </section>

      {/* Section 3: 行動プロファイル */}
      <ProfileInfo />
    </section>
  );
}
