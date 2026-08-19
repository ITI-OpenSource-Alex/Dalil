"use client";

import { useState } from "react";
import { Search, Trash2 } from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Field,
  Input,
  Modal,
  ModalContent,
  Radio,
  RadioGroup,
  Select,
  Switch,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
  Text,
  Textarea,
  Tooltip,
  TooltipProvider,
} from "@/components/ui";

/**
 * The stateful half of the style guide. Kept in its own client module so the
 * page shell itself stays a Server Component -- the same split every real
 * page should use.
 */
export function InteractiveExamples() {
  const [checked, setChecked] = useState(true);
  const [mixed, setMixed] = useState(true);
  const [switchOn, setSwitchOn] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [blockingOpen, setBlockingOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  return (
    <TooltipProvider>
      <div className="flex flex-col gap-10">
        {/* -------------------------------------------------- Form controls */}
        <div className="grid gap-6 sm:grid-cols-2">
          <Field label="Email" hint="We'll never share it.">
            <Input type="email" placeholder="you@university.edu" />
          </Field>

          <Field label="Search" >
            <Input placeholder="Find a programme" leadingIcon={Search} />
          </Field>

          <Field
            label="Password"
            error="Password must be at least 8 characters."
          >
            <Input type="password" defaultValue="short" />
          </Field>

          <Field label="Target country" required>
            <Select placeholder="Choose a country" defaultValue="">
              <option value="de">Germany</option>
              <option value="nl">Netherlands</option>
              <option value="se">Sweden</option>
            </Select>
          </Field>

          <Field label="Disabled" hint="Not editable in this plan.">
            <Input defaultValue="Locked value" disabled />
          </Field>

          <Field label="Statement of purpose">
            <Textarea placeholder="Tell us why…" rows={3} />
          </Field>
        </div>

        {/* -------------------------------------------------- Toggles */}
        <div className="grid gap-6 sm:grid-cols-3">
          <div className="flex flex-col gap-3">
            <Text size="sm" tone="subtle" weight="medium">
              Checkbox
            </Text>
            <Checkbox
              checked={checked}
              onChange={setChecked}
              description="Applies to all four skills."
            >
              Enable IELTS reminders
            </Checkbox>
            <Checkbox
              indeterminate={mixed}
              checked={false}
              onChange={() => setMixed(false)}
            >
              Mixed selection
            </Checkbox>
            <Checkbox checked disabled>
              Disabled, checked
            </Checkbox>
          </div>

          <div className="flex flex-col gap-3">
            <RadioGroup legend="Degree level" name="degree">
              <Radio value="bsc" defaultChecked description="Undergraduate">
                Bachelor&apos;s
              </Radio>
              <Radio value="msc" description="Postgraduate">
                Master&apos;s
              </Radio>
              <Radio value="phd" disabled>
                Doctorate
              </Radio>
            </RadioGroup>
          </div>

          <div className="flex flex-col gap-3">
            <Text size="sm" tone="subtle" weight="medium">
              Switch
            </Text>
            <Switch
              checked={switchOn}
              onChange={setSwitchOn}
              description="Applies immediately."
            >
              Email notifications
            </Switch>
            <Switch checked={false} disabled>
              Disabled
            </Switch>
          </div>
        </div>

        {/* -------------------------------------------------- Tabs */}
        {/* min-w-0 on grid children: grid items default to min-width:auto,
            which lets their content stretch the track past the viewport. */}
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <Text size="sm" tone="subtle" weight="medium" className="mb-3">
              Tabs — underline
            </Text>
            <Tabs defaultValue="reading">
              <TabsList>
                <TabsTrigger value="reading">Reading</TabsTrigger>
                <TabsTrigger value="writing">Writing</TabsTrigger>
                <TabsTrigger value="speaking">Speaking</TabsTrigger>
                <TabsTrigger value="listening" disabled>
                  Listening
                </TabsTrigger>
              </TabsList>
              <TabsPanel value="reading">
                <Text size="sm" tone="muted">
                  Arrow keys move between tabs; Home and End jump to the ends.
                </Text>
              </TabsPanel>
              <TabsPanel value="writing">
                <Text size="sm" tone="muted">
                  Writing panel.
                </Text>
              </TabsPanel>
              <TabsPanel value="speaking">
                <Text size="sm" tone="muted">
                  Speaking panel.
                </Text>
              </TabsPanel>
            </Tabs>
          </div>

          <div className="min-w-0">
            <Text size="sm" tone="subtle" weight="medium" className="mb-3">
              Tabs — pill
            </Text>
            <Tabs defaultValue="academic">
              <TabsList variant="pill">
                <TabsTrigger value="academic">Academic</TabsTrigger>
                <TabsTrigger value="general">General Training</TabsTrigger>
              </TabsList>
              <TabsPanel value="academic">
                <Text size="sm" tone="muted">
                  Academic module.
                </Text>
              </TabsPanel>
              <TabsPanel value="general">
                <Text size="sm" tone="muted">
                  General Training module.
                </Text>
              </TabsPanel>
            </Tabs>
          </div>
        </div>

        {/* -------------------------------------------------- Overlays */}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => setModalOpen(true)}>Open modal</Button>
          <Button variant="danger" onClick={() => setBlockingOpen(true)}>
            Open blocking modal
          </Button>

          <Tooltip content="Tooltips are supplementary — never the only source of an instruction.">
            <Button variant="secondary">Hover or focus me</Button>
          </Tooltip>

          <Tooltip content="Permanently deletes this session." side="right">
            <Button variant="ghost" size="md" iconOnly aria-label="Delete session">
              <Trash2 size={16} />
            </Button>
          </Tooltip>

          <Badge tone="success" dot live>
            Live
          </Badge>
        </div>

        {!dismissed && (
          <Alert
            tone="info"
            title="Dismissible alert"
            onDismiss={() => setDismissed(true)}
          >
            Dismissal is controlled by the caller, which is what lets Alert stay
            server-renderable when it is static.
          </Alert>
        )}

        <Modal open={modalOpen} onOpenChange={setModalOpen}>
          <ModalContent
            title="Submit your exam?"
            description="You have 3 unanswered questions."
            footer={
              <>
                <Button variant="secondary" onClick={() => setModalOpen(false)}>
                  Keep working
                </Button>
                <Button onClick={() => setModalOpen(false)}>Submit exam</Button>
              </>
            }
          >
            <Text size="sm" tone="muted">
              Focus is trapped inside this dialog and returns to the trigger on
              close. Escape and the overlay both dismiss it.
            </Text>
          </ModalContent>
        </Modal>

        <Modal open={blockingOpen} onOpenChange={setBlockingOpen}>
          <ModalContent
            title="Delete your saved data?"
            description="This cannot be undone."
            dismissible={false}
            hideCloseButton
            size="sm"
            footer={
              <>
                <Button
                  variant="secondary"
                  onClick={() => setBlockingOpen(false)}
                >
                  Cancel
                </Button>
                <Button variant="danger" onClick={() => setBlockingOpen(false)}>
                  Delete everything
                </Button>
              </>
            }
          >
            <Text size="sm" tone="muted">
              Escape and overlay-click are disabled here, so the choice has to
              be made explicitly. Reserved for destructive confirmations.
            </Text>
          </ModalContent>
        </Modal>
      </div>
    </TooltipProvider>
  );
}
