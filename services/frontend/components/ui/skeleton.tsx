interface SkeletonProps {
  /**
   * Overrides the default single-text-line sizing (h-4 w-full) so this
   * component can also stand in for block-shaped loading regions (cards,
   * banners) -- doc 11. Existing callers that pass no className keep the
   * exact same rendered output as before this change.
   */
  className?: string;
}

export default function Skeleton({ className = "h-4 w-full" }: SkeletonProps) {
  return <div className={`animate-pulse rounded-md bg-gray-200 ${className}`} />;
}
