"use client";

import { motion } from "framer-motion";
import ReactMarkdown, { type Components } from "react-markdown";

interface StreamingMessageProps {
  content: string;
  isStreaming?: boolean;
  streamingStatus?: string;
  /** Assistant responses use bounded Markdown; user-authored text stays literal. */
  markdown?: boolean;
}

function StreamingStatus({ label }: { label: string }) {
  return (
    <motion.div
      role="status"
      aria-live="polite"
      aria-label={label}
      initial={{ opacity: 0, y: 3 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex min-w-52 items-center gap-3 py-0.5 text-sm text-fg-muted"
    >
      <span className="flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <motion.span
            key={index}
            className="h-2 w-2 rounded-full bg-brand"
            animate={{ y: [0, -5, 0], opacity: [0.45, 1, 0.45] }}
            transition={{
              duration: 0.9,
              repeat: Infinity,
              delay: index * 0.14,
              ease: "easeInOut",
            }}
          />
        ))}
      </span>
      <motion.span
        key={label}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        {label}
      </motion.span>
    </motion.div>
  );
}

const markdownComponents: Components = {
  p: ({ children }) => (
    <p className="mb-3 leading-6 last:mb-0">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-fg">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-base font-bold text-fg first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-sm font-bold text-fg first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-sm font-semibold text-fg first:mt-0">
      {children}
    </h3>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 ml-5 list-disc space-y-1.5 marker:text-brand last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 ml-5 list-decimal space-y-1.5 marker:font-semibold marker:text-brand-fg last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1 leading-6">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-r-control border-l-2 border-brand bg-brand-subtle px-3 py-2 text-fg-muted">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) =>
    className ? (
      <code className="my-3 block max-w-full overflow-x-auto rounded-control bg-canvas-inset p-3 font-mono text-xs leading-5 text-fg">
        {children}
      </code>
    ) : (
      <code className="rounded bg-canvas-inset px-1.5 py-0.5 font-mono text-[0.85em] text-brand-fg">
        {children}
      </code>
    ),
  a: ({ children, href }) => {
    const safeHref = href && /^(https?:|mailto:)/i.test(href) ? href : undefined;
    return safeHref ? (
      <a
        href={safeHref}
        target="_blank"
        rel="noreferrer noopener"
        className="font-medium text-brand-fg underline decoration-brand-border underline-offset-2 hover:decoration-brand"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    );
  },
  hr: () => <hr className="my-4 border-border" />,
};

function StreamingCursor() {
  return (
    <motion.span
      aria-hidden="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: [0, 1, 0] }}
      transition={{
        duration: 1,
        repeat: Infinity,
        ease: "easeInOut",
      }}
      className="ml-1 inline-block h-4 w-0.5 rounded-full bg-brand align-middle"
    />
  );
}

export default function StreamingMessage({
  content,
  isStreaming = false,
  streamingStatus,
  markdown = false,
}: StreamingMessageProps) {
  if (isStreaming && !content && streamingStatus) {
    return <StreamingStatus label={streamingStatus} />;
  }
  if (markdown) {
    return (
      <div className="min-w-0 wrap-break-word text-sm leading-6">
        <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
        {isStreaming && <StreamingCursor />}
      </div>
    );
  }

  return (
    <div className="relative">
      <p className="whitespace-pre-wrap wrap-break-word leading-relaxed">
        {content}
        {isStreaming && <StreamingCursor />}
      </p>
    </div>
  );
}
