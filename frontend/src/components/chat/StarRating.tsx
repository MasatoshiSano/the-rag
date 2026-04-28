import { useState, useCallback } from "react";
import { rateMessage } from "../../api/chat";

interface StarRatingProps {
  messageId: string;
  initialRating: number | null;
}

export function StarRating({ messageId, initialRating }: StarRatingProps) {
  const [rating, setRating] = useState<number | null>(initialRating);
  const [hovered, setHovered] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRate = useCallback(
    async (value: number) => {
      if (isSubmitting) return;
      setIsSubmitting(true);
      try {
        await rateMessage(messageId, value);
        setRating(value);
      } catch (err) {
        console.error("評価の送信に失敗しました", err);
      } finally {
        setIsSubmitting(false);
      }
    },
    [messageId, isSubmitting]
  );

  const effectiveRating = hovered ?? rating ?? 0;

  return (
    <div
      role="radiogroup"
      aria-label="回答を評価"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sds-spacing-extra-small, 4px)",
      }}
    >
      {[1, 2, 3, 4, 5].map((star) => {
        const isActive = star <= effectiveRating;
        const isSelected = star === rating;

        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={isSelected}
            aria-label={`${star}星`}
            disabled={isSubmitting}
            onClick={() => handleRate(star)}
            onMouseEnter={() => setHovered(star)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(star)}
            onBlur={() => setHovered(null)}
            style={{
              background: "none",
              border: "none",
              cursor: isSubmitting ? "not-allowed" : "pointer",
              padding: "2px",
              color: isActive
                ? "var(--sds-color-primary-default)"
                : "var(--sds-color-on-surface-low)",
              fontSize: 18,
              lineHeight: 1,
              borderRadius: "var(--sds-border-radius-extra-small, 4px)",
              transition: "color 0.15s ease",
              outline: "none",
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleRate(star);
              }
            }}
          >
            <span aria-hidden="true">{isActive ? "★" : "☆"}</span>
          </button>
        );
      })}
    </div>
  );
}
