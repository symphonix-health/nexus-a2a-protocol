// ─────────────────────────────────────────────────────────────────────────────
// Design System Showcase
// Drop this page into your app to see every component in one place.
// Route it at /showcase (or /design) — remove it before shipping to prod.
// ─────────────────────────────────────────────────────────────────────────────

"use client";

import React, { useState } from "react";
import {
  Search, Bell, Shield, AlertTriangle, Info, CheckCircle, XCircle, Plus, Download,
  Activity, Key, Zap, Server,
} from "lucide-react";
import {
  Button, Badge, Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
  Input, Select, Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
  Tabs, TabList, Tab, TabPanel,
  StatusDot, Skeleton, SkeletonText, SkeletonCard, EmptyState,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "./components/ui";
import {
  MetricCard, AreaChartCard, BarChartCard, DonutChart, SloGauge,
  SparklineChart, LatencyHistogram,
} from "./components/charts";

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-50 border-b border-surface-200 dark:border-surface-700 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

// ── Main showcase ─────────────────────────────────────────────────────────────
export default function Showcase() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [inputError, setInputError] = useState("");

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950 py-12">
      <div className="mx-auto max-w-4xl px-6 space-y-14">

        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-surface-900 dark:text-surface-50">
            <span className="text-gradient-brand">Design System</span> Showcase
          </h1>
          <p className="mt-2 text-surface-500 dark:text-surface-400">
            Every component, every variant, in one place.
          </p>
        </div>

        {/* ── Buttons ─────────────────────────────────────────────────────── */}
        <Section title="Button">
          <div className="flex flex-wrap gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large</Button>
            <Button size="icon" aria-label="Add"><Plus className="h-4 w-4" /></Button>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button loading>Saving…</Button>
            <Button disabled>Disabled</Button>
          </div>
        </Section>

        {/* ── Badges ──────────────────────────────────────────────────────── */}
        <Section title="Badge">
          <div className="flex flex-wrap gap-2">
            <Badge>Default</Badge>
            <Badge variant="success">Success</Badge>
            <Badge variant="warning">Warning</Badge>
            <Badge variant="danger">Danger</Badge>
            <Badge variant="info">Info</Badge>
            <Badge variant="outline">Outline</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="success" dot>Active</Badge>
            <Badge variant="warning" dot>Degraded</Badge>
            <Badge variant="danger" dot>Critical</Badge>
            <Badge variant="info" dot>Info</Badge>
          </div>
        </Section>

        {/* ── Status Dots ─────────────────────────────────────────────────── */}
        <Section title="StatusDot">
          <div className="flex flex-wrap items-center gap-6">
            {["healthy", "degraded", "critical", "unknown", "active", "suspended", "revoked", "connected", "disconnected"].map((s) => (
              <div key={s} className="flex items-center gap-2">
                <StatusDot status={s} size="md" />
                <span className="text-sm text-surface-600 dark:text-surface-400 capitalize">{s}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-6">
            <StatusDot status="active" pulse size="sm" />
            <StatusDot status="active" pulse size="md" />
            <StatusDot status="critical" pulse size="lg" />
            <span className="text-sm text-surface-500">← with pulse animation</span>
          </div>
        </Section>

        {/* ── Cards ───────────────────────────────────────────────────────── */}
        <Section title="Card">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Default Card</CardTitle>
                <CardDescription>Subtle shadow, clean border</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-surface-600 dark:text-surface-400">Body content goes here.</p>
              </CardContent>
              <CardFooter className="justify-end">
                <Button size="sm" variant="outline">Action</Button>
              </CardFooter>
            </Card>

            <Card variant="interactive">
              <CardHeader>
                <CardTitle>Interactive Card</CardTitle>
                <CardDescription>Hover for brand-tinted border + shadow lift</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-surface-600 dark:text-surface-400">Clickable surface.</p>
              </CardContent>
            </Card>

            <Card variant="elevated">
              <CardHeader>
                <CardTitle>Elevated Card</CardTitle>
                <CardDescription>Stronger shadow for modals / popovers</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-surface-600 dark:text-surface-400">Lifted off the page.</p>
              </CardContent>
            </Card>

            <Card variant="glass">
              <CardHeader>
                <CardTitle>Glass Card</CardTitle>
                <CardDescription>Frosted glass for hero sections</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-surface-600 dark:text-surface-400">backdrop-blur-xl</p>
              </CardContent>
            </Card>
          </div>
        </Section>

        {/* ── Inputs ──────────────────────────────────────────────────────── */}
        <Section title="Input & Select">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input label="Display Name" placeholder="e.g., Radiology AI Summarizer" />
            <Input label="Search" placeholder="Search…" prefix={<Search className="h-4 w-4" />} />
            <Input
              label="With helper"
              placeholder="Enter value"
              helperText="Must be unique across the registry"
            />
            <Input
              label="With error"
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                setInputError(e.target.value.length < 3 ? "Minimum 3 characters" : "");
              }}
              error={inputError}
              placeholder="Validate on change"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select label="Jurisdiction">
              <option value="">All Jurisdictions</option>
              <option value="IE">IE — Ireland</option>
              <option value="GB">GB — United Kingdom</option>
              <option value="US">US — United States</option>
            </Select>
            <Select label="Status">
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="revoked">Revoked</option>
            </Select>
          </div>
        </Section>

        {/* ── Tabs ────────────────────────────────────────────────────────── */}
        <Section title="Tabs">
          <Card>
            <CardContent className="pt-6">
              <Tabs defaultValue="overview">
                <TabList>
                  <Tab value="overview">Overview</Tab>
                  <Tab value="endpoints">Endpoints</Tab>
                  <Tab value="trust">Trust</Tab>
                  <Tab value="audit">Audit Log</Tab>
                </TabList>
                <TabPanel value="overview">
                  <p className="text-sm text-surface-600 dark:text-surface-400">Overview panel content.</p>
                </TabPanel>
                <TabPanel value="endpoints">
                  <p className="text-sm text-surface-600 dark:text-surface-400">Endpoints panel content.</p>
                </TabPanel>
                <TabPanel value="trust">
                  <p className="text-sm text-surface-600 dark:text-surface-400">Trust panel content.</p>
                </TabPanel>
                <TabPanel value="audit">
                  <p className="text-sm text-surface-600 dark:text-surface-400">Audit log panel content.</p>
                </TabPanel>
              </Tabs>
            </CardContent>
          </Card>
        </Section>

        {/* ── Dialog ──────────────────────────────────────────────────────── */}
        <Section title="Dialog">
          <div className="flex gap-3">
            <Button onClick={() => setDialogOpen(true)}>Open Dialog</Button>
          </div>
          <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
            <DialogContent size="md">
              <DialogTitle>Confirm Registration</DialogTitle>
              <DialogDescription>
                Review the details below before registering the agent to the global registry.
              </DialogDescription>
              <div className="px-6 py-2 space-y-2">
                {[["Name", "Radiology AI Summarizer"], ["Jurisdiction", "US"], ["Protocol", "FHIR R4"]].map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-surface-500">{k}</span>
                    <span className="font-medium text-surface-900 dark:text-surface-100">{v}</span>
                  </div>
                ))}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button onClick={() => setDialogOpen(false)}>Register Agent</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </Section>

        {/* ── Skeletons ───────────────────────────────────────────────────── */}
        <Section title="Skeleton">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SkeletonCard />
            <div className="space-y-3 pt-4">
              <Skeleton variant="text" className="w-1/3 h-5" />
              <SkeletonText lines={4} />
              <Skeleton variant="rect" className="h-9 w-28" />
            </div>
          </div>
        </Section>

        {/* ── Empty State ─────────────────────────────────────────────────── */}
        <Section title="EmptyState">
          <Card>
            <EmptyState
              icon={<Search className="h-6 w-6" />}
              title="No agents found"
              description="Try adjusting your search filters or register a new agent to get started."
              action={<Button size="sm"><Plus className="h-4 w-4" />Register Agent</Button>}
            />
          </Card>
        </Section>

        {/* ── Table ───────────────────────────────────────────────────────── */}
        <Section title="Table">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Jurisdiction</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead className="text-right">Requests</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[
                    { name: "Radiology AI Summarizer", jurisdiction: "US", status: "active", tier: "Enterprise", requests: "1,204,831" },
                    { name: "Pathology Triage Agent", jurisdiction: "GB", status: "active", tier: "Professional", requests: "543,210" },
                    { name: "Lab Results Parser", jurisdiction: "IE", status: "suspended", tier: "Starter", requests: "87,654" },
                    { name: "Consent Validator", jurisdiction: "DE", status: "revoked", tier: "Enterprise", requests: "0" },
                  ].map((row) => (
                    <TableRow key={row.name}>
                      <TableCell className="font-medium text-surface-900 dark:text-surface-50">{row.name}</TableCell>
                      <TableCell>{row.jurisdiction}</TableCell>
                      <TableCell>
                        <Badge
                          variant={row.status === "active" ? "success" : row.status === "suspended" ? "warning" : "danger"}
                          dot
                        >
                          {row.status}
                        </Badge>
                      </TableCell>
                      <TableCell><Badge variant="outline">{row.tier}</Badge></TableCell>
                      <TableCell className="text-right font-mono text-xs">{row.requests}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Section>

        {/* ── Charts — MetricCard ───────────────────────────────────────────── */}
        <Section title="MetricCard">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Total Agents"
              value={1247}
              icon={<Server className="h-5 w-5" />}
              trend={{ value: 12, label: "vs last month" }}
            />
            <MetricCard
              title="API Keys"
              value={384}
              icon={<Key className="h-5 w-5" />}
              trend={{ value: -3, label: "vs last week" }}
              gradient="bg-gradient-to-br from-indigo-500 to-indigo-700"
            />
            <MetricCard
              title="Requests / min"
              value="8.4k"
              icon={<Zap className="h-5 w-5" />}
              sparkline={[
                { ts: "1", value: 40 }, { ts: "2", value: 55 }, { ts: "3", value: 48 },
                { ts: "4", value: 62 }, { ts: "5", value: 58 }, { ts: "6", value: 84 },
              ]}
            />
            <MetricCard
              title="Uptime"
              value="99.94%"
              icon={<Activity className="h-5 w-5" />}
              ring={{ percent: 99, color: "#10b981" }}
            />
          </div>
        </Section>

        {/* ── Charts — AreaChartCard ─────────────────────────────────────────── */}
        <Section title="AreaChartCard">
          <AreaChartCard
            title="Requests Over Time"
            description="Hourly request volume for the past 24 hours"
            data={[
              { time: "00:00", requests: 120, errors: 2 },
              { time: "04:00", requests: 80, errors: 1 },
              { time: "08:00", requests: 340, errors: 5 },
              { time: "12:00", requests: 520, errors: 8 },
              { time: "16:00", requests: 480, errors: 6 },
              { time: "20:00", requests: 310, errors: 3 },
              { time: "24:00", requests: 150, errors: 2 },
            ]}
            dataKey="requests"
            secondaryDataKey="errors"
            secondaryColor="#ef4444"
            height={220}
          />
        </Section>

        {/* ── Charts — BarChartCard ──────────────────────────────────────────── */}
        <Section title="BarChartCard">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <BarChartCard
              title="Agents by Jurisdiction"
              data={[
                { name: "US", count: 420 },
                { name: "GB", count: 310 },
                { name: "DE", count: 180 },
                { name: "IE", count: 95 },
                { name: "FR", count: 72 },
              ]}
              dataKey="count"
              colorByIndex
              height={200}
            />
            <BarChartCard
              title="Top Protocols"
              data={[
                { name: "FHIR R4", count: 640 },
                { name: "HL7v2", count: 280 },
                { name: "JSON-RPC", count: 190 },
                { name: "REST", count: 137 },
              ]}
              dataKey="count"
              layout="vertical"
              height={200}
            />
          </div>
        </Section>

        {/* ── Charts — DonutChart ────────────────────────────────────────────── */}
        <Section title="DonutChart">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <DonutChart
              title="Agent Status Distribution"
              data={[
                { name: "Active", value: 842 },
                { name: "Suspended", value: 56 },
                { name: "Revoked", value: 23 },
                { name: "Retired", value: 104 },
              ]}
              colors={["#10b981", "#f59e0b", "#ef4444", "#94a3b8"]}
              centerSubLabel="agents"
              height={220}
            />
            <DonutChart
              title="Traffic by Tier"
              data={[
                { name: "Enterprise", value: 68 },
                { name: "Professional", value: 22 },
                { name: "Starter", value: 10 },
              ]}
              centerLabel="100%"
              centerSubLabel="of traffic"
              height={220}
            />
          </div>
        </Section>

        {/* ── Charts — SloGauge ──────────────────────────────────────────────── */}
        <Section title="SloGauge">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SloGauge
              title="API Availability SLO"
              target={0.999}
              current={0.9994}
              budgetRemaining={0.72}
              totalRequests={1842567}
              totalErrors={1105}
            />
            <SloGauge
              title="Latency P99 SLO"
              target={0.995}
              current={0.9812}
              budgetRemaining={0.12}
              totalRequests={1842567}
              totalErrors={34675}
            />
          </div>
        </Section>

        {/* ── Charts — LatencyHistogram ──────────────────────────────────────── */}
        <Section title="LatencyHistogram">
          <LatencyHistogram
            title="Request Latency Distribution"
            description="Cumulative histogram buckets — colour shifts from green to red as latency increases"
            buckets={[
              { le: "0.01", count: 420 },
              { le: "0.05", count: 1230 },
              { le: "0.1", count: 2800 },
              { le: "0.25", count: 4100 },
              { le: "0.5", count: 4600 },
              { le: "1", count: 4820 },
              { le: "2.5", count: 4900 },
              { le: "5", count: 4950 },
              { le: "+Inf", count: 5000 },
            ]}
          />
        </Section>

        {/* ── Charts — SparklineChart ────────────────────────────────────────── */}
        <Section title="SparklineChart">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-surface-600 dark:text-surface-400 mb-4">
                Inline sparklines for embedding in tables, lists, or KPI rows:
              </p>
              <div className="flex items-center gap-8">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-surface-700 dark:text-surface-300">CPU</span>
                  <SparklineChart data={[{ value: 30 }, { value: 45 }, { value: 38 }, { value: 52 }, { value: 48 }, { value: 60 }]} />
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-surface-700 dark:text-surface-300">Memory</span>
                  <SparklineChart data={[{ value: 70 }, { value: 72 }, { value: 68 }, { value: 75 }, { value: 80 }, { value: 78 }]} color="#6366f1" />
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-surface-700 dark:text-surface-300">Errors</span>
                  <SparklineChart data={[{ value: 5 }, { value: 8 }, { value: 3 }, { value: 12 }, { value: 6 }, { value: 2 }]} color="#ef4444" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Section>

        {/* ── Utility classes ─────────────────────────────────────────────── */}
        <Section title="Utility Classes">
          <div className="flex flex-wrap gap-4">
            <div className="px-4 py-2 rounded-lg text-white glow-brand bg-brand-600">
              .glow-brand
            </div>
            <div className="px-4 py-2 rounded-lg glass text-surface-700 dark:text-surface-200">
              .glass
            </div>
            <span className="text-2xl font-bold text-gradient-brand">.text-gradient-brand</span>
          </div>
        </Section>

      </div>
    </div>
  );
}
