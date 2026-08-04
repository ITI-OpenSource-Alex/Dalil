/**
 * GOA UI primitives.
 *
 * Import from "@/components/ui" rather than reaching into individual files,
 * so the surface of the design system stays visible in one place.
 *
 * Server-renderable (no "use client"): Button, Card, Badge, Alert, Heading,
 * Text, Icon, Spinner, Skeleton, Progress, EmptyState. Marketing pages built
 * from these ship zero client JS.
 *
 * Client-only (hooks or Radix): Field, Input, Textarea, Select, Checkbox,
 * Radio, Switch, Modal, Tabs, Tooltip.
 *
 * Token reference: docs/DESIGN-TOKENS.md
 */

export { Button } from "./button";
export type { ButtonProps, ButtonSize, ButtonVariant } from "./button";

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardBody,
  CardFooter,
} from "./card";
export type { CardProps, CardVariant, CardFooterProps } from "./card";

export { Badge } from "./badge";
export type { BadgeProps, BadgeTone, BadgeVariant } from "./badge";

export { Alert } from "./alert";
export type { AlertProps, AlertTone } from "./alert";

export { Heading } from "./heading";
export type { HeadingProps, HeadingSize } from "./heading";

export { Text, Eyebrow } from "./text";
export type { TextProps, TextSize, TextTone } from "./text";

export { Icon, ICON_SIZE } from "./icon";
export type { IconProps, IconSize } from "./icon";

export { Spinner } from "./spinner";
export type { SpinnerProps } from "./spinner";

export { Skeleton, SkeletonGroup } from "./skeleton";
export type { SkeletonProps } from "./skeleton";

export { Progress } from "./progress";
export type { ProgressProps } from "./progress";

export { EmptyState } from "./empty-state";
export type { EmptyStateProps } from "./empty-state";

export { PageContainer } from "./page-container";
export type { PageContainerProps } from "./page-container";

export { Field, useFieldControl } from "./field";
export type { FieldProps, FieldControlProps } from "./field";

export {
  Input,
  Textarea,
  Select,
  CONTROL_BASE,
  CONTROL_VALID,
  CONTROL_INVALID,
} from "./input";
export type { InputProps, TextareaProps, SelectProps, InputSize } from "./input";

export { Checkbox } from "./checkbox";
export type { CheckboxProps } from "./checkbox";

export { Radio, RadioGroup } from "./radio";
export type { RadioProps, RadioGroupProps } from "./radio";

export { Switch } from "./switch";
export type { SwitchProps } from "./switch";

export { Modal, ModalContent, ModalTrigger, ModalClose } from "./modal";
export type { ModalProps, ModalContentProps } from "./modal";

export { Tabs, TabsList, TabsTrigger, TabsPanel } from "./tabs";
export type { TabsListProps, TabsVariant } from "./tabs";

export { Tooltip, TooltipProvider } from "./tooltip";
export type { TooltipProps } from "./tooltip";
