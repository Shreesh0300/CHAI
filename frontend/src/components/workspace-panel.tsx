"use client"

import { ArrowDownRight, ArrowUpRight, Check, Info } from "lucide-react"
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts"
import type { WorkArtifact } from "@/components/chat-types"
import { chartConfig } from "@/components/chat-types"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

export function WorkResults({ artifact }: { artifact: WorkArtifact }) {
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2 px-1 pt-1">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="gap-1.5 border-primary/20 bg-primary/5 text-primary">
            <Check data-icon="inline-start" />
            Work completed
          </Badge>
        </div>
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {artifact.title}
        </h1>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
          {artifact.subtitle}
        </p>
      </section>

      <Marker className="rounded-xl border border-border/80 bg-muted/45 px-3 py-2.5 text-xs leading-5">
        <MarkerIcon>
          <Info aria-hidden="true" />
        </MarkerIcon>
        <MarkerContent>
          Example workspace only: all figures are illustrative sample data, not live results.
        </MarkerContent>
      </Marker>

      <section aria-label="Summary metrics" className="grid grid-cols-1 gap-2.5 min-[480px]:grid-cols-3 sm:gap-3">
        {artifact.metrics.map((metric) => {
          const isNegative = metric.change.startsWith("−") || metric.change.startsWith("-")
          const ChangeIcon = isNegative ? ArrowDownRight : ArrowUpRight

          return (
            <Card key={metric.label} className="gap-1 rounded-xl border-border/80 py-3 shadow-none">
              <CardHeader className="gap-1 px-3 py-0 sm:px-3.5">
                <CardDescription className="min-h-5 text-[10px] leading-4 sm:text-xs">
                  {metric.label}
                </CardDescription>
                <CardTitle className="text-[1.1rem] leading-tight tracking-tight sm:text-xl">
                  {metric.value}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-1 px-3 pb-0 text-[9px] sm:px-3.5 sm:text-[10px]">
                <span className={cn("inline-flex items-center gap-0.5 font-medium", isNegative ? "text-muted-foreground" : "text-primary")}>
                  <ChangeIcon aria-hidden="true" className="size-3" />
                  {metric.change}
                </span>
                <span className="text-muted-foreground">{metric.note}</span>
              </CardContent>
            </Card>
          )
        })}
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <Card className="gap-0 rounded-2xl border-border/80 py-0 shadow-none">
          <CardHeader className="flex flex-row items-start justify-between gap-3 px-4 pb-0 pt-4">
            <div className="grid gap-1">
              <CardTitle className="text-sm">Activity over time</CardTitle>
              <CardDescription className="text-xs">Current signal against a benchmark</CardDescription>
            </div>
            <Badge variant="secondary" className="shrink-0 text-[10px]">6 weeks</Badge>
          </CardHeader>
          <CardContent className="px-3 pb-3 pt-2 sm:px-4">
            <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[10px] text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-chart-1" aria-hidden="true" /> Current signal
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-chart-2" aria-hidden="true" /> Benchmark
              </span>
            </div>
            <ChartContainer config={chartConfig} className="h-[210px] w-full aspect-auto sm:h-[240px]">
              <LineChart
                data={artifact.chartData}
                margin={{ top: 8, right: 8, bottom: 0, left: 4 }}
              >
                <CartesianGrid vertical={false} strokeDasharray="4 4" />
                <XAxis
                  dataKey="week"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tick={{ fontSize: 10 }}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  tickMargin={6}
                  tick={{ fontSize: 10 }}
                  width={38}
                />
                <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
                <Line
                  type="monotone"
                  dataKey="current"
                  stroke="var(--color-current)"
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  stroke="var(--color-benchmark)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card className="gap-0 rounded-2xl border-border/80 py-0 shadow-none">
          <CardHeader className="px-4 pb-0 pt-4">
            <CardTitle className="text-sm">Channel breakdown</CardTitle>
            <CardDescription className="text-xs">Share and period-over-period change</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto px-2 pb-3 pt-2 sm:px-3">
            <Table aria-label="Illustrative channel breakdown" className="min-w-[340px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-9 text-[10px]">Source</TableHead>
                  <TableHead className="h-9 text-right text-[10px]">Share</TableHead>
                  <TableHead className="h-9 text-right text-[10px]">Change</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {artifact.rows.map((row) => (
                  <TableRow key={row.source}>
                    <TableCell className="py-2.5">
                      <div className="font-medium text-foreground">{row.source}</div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">{row.description}</div>
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{row.share}%</TableCell>
                    <TableCell className="text-right text-xs font-medium text-primary">{row.change}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="gap-3 rounded-2xl border-border/80 py-4 shadow-none">
          <CardHeader className="px-4 py-0">
            <CardTitle className="text-sm">Key takeaways</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-0">
            <ul className="flex flex-col gap-2.5">
              {artifact.highlights.map((highlight) => (
                <li key={highlight} className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                  <Check aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-primary" />
                  <span>{highlight}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="gap-3 rounded-2xl border-border/80 py-4 shadow-none">
          <CardHeader className="px-4 py-0">
            <CardTitle className="text-sm">Suggested next steps</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-0">
            <ol className="flex flex-col gap-2.5">
              {artifact.nextSteps.map((step, index) => (
                <li key={step} className="flex items-start gap-2.5 text-xs leading-5 text-muted-foreground">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[10px] font-semibold text-foreground">
                    {index + 1}
                  </span>
                  <span className="pt-0.5">{step}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
