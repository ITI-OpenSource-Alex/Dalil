import type { ReactNode } from "react";
import { Heading, Text } from "@/components/ui";
import type { ProfileSectionId } from "@/lib/profile-readiness";

/**
 * A titled group of form fields with a stable anchor id.
 *
 * The id is what the completeness card scrolls to, so it is typed against the
 * same union the readiness helper hands out — a section that nothing can link
 * to, or a link to a section that does not exist, both fail to compile.
 */
export function FormSection({
  id,
  title,
  description,
  children,
}: {
  id: ProfileSectionId | "profile-section-experience";
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="flex scroll-mt-24 flex-col gap-5 border-t border-border pt-6 first:border-t-0 first:pt-0"
    >
      <div>
        <Heading as="h3" size="xs" id={`${id}-heading`}>
          {title}
        </Heading>
        {description && (
          <Text size="sm" tone="muted" className="mt-1">
            {description}
          </Text>
        )}
      </div>
      {children}
    </section>
  );
}
