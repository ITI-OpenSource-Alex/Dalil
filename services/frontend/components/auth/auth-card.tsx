import { Heading, Text } from "@/components/ui";

/**
 * The heading + card chrome shared by every page inside app/(auth). Pulled
 * out of the layout (rather than folded into it) because each page's title
 * and subtitle differ, but the spacing and card treatment must not.
 */
export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-8">
        <Heading as="h1" size="xl">
          {title}
        </Heading>
        {subtitle && (
          <Text size="base" tone="muted" className="mt-2">
            {subtitle}
          </Text>
        )}
      </div>

      <div className="rounded-panel border border-border bg-surface p-6 shadow-e1 sm:p-8">
        {children}
      </div>
    </div>
  );
}
