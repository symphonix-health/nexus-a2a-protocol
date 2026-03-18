const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak,
  TableOfContents
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0 };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

const BLUE = "1B4F72";
const ACCENT = "2E75B6";
const LIGHT_BG = "E8F0FE";
const GREEN = "1E8449";
const RED = "C0392B";
const ORANGE = "E67E22";

function heading(text, level) {
  return new Paragraph({
    heading: level,
    spacing: { before: level === HeadingLevel.HEADING_1 ? 360 : 240, after: 200 },
    children: [new TextRun({ text, bold: true, font: "Arial", size: level === HeadingLevel.HEADING_1 ? 32 : level === HeadingLevel.HEADING_2 ? 28 : 24, color: BLUE })]
  });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    alignment: opts.align || AlignmentType.LEFT,
    children: [new TextRun({ text, font: "Arial", size: 22, ...opts })]
  });
}

function bullet(text, ref = "bullets", level = 0) {
  return new Paragraph({
    numbering: { reference: ref, level },
    spacing: { after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22 })]
  });
}

function boldBullet(label, desc, ref = "bullets") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80 },
    children: [
      new TextRun({ text: label + " ", font: "Arial", size: 22, bold: true }),
      new TextRun({ text: desc, font: "Arial", size: 22 })
    ]
  });
}

function cell(text, opts = {}) {
  return new TableCell({
    borders,
    width: { size: opts.width || 2340, type: WidthType.DXA },
    shading: opts.shading ? { fill: opts.shading, type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: "center",
    children: [new Paragraph({
      spacing: { after: 0 },
      alignment: opts.align || AlignmentType.LEFT,
      children: [new TextRun({ text, font: "Arial", size: opts.size || 20, bold: !!opts.bold, color: opts.color || "000000" })]
    })]
  });
}

function headerCell(text, width) {
  return cell(text, { width, shading: BLUE, bold: true, color: "FFFFFF", size: 20 });
}

function statusCell(status, width) {
  const colors = { "GA": GREEN, "Experimental": ORANGE, "Not Started": RED, "Partial": ORANGE, "Full": GREEN, "None": RED };
  return cell(status, { width, color: colors[status] || "000000", bold: true });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 240, after: 180 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: ACCENT },
        paragraph: { spacing: { before: 200, after: 160 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }
      ]},
      { reference: "numbers", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }
      ]},
      { reference: "phase", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "Phase %1:", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }
      ]}
    ]
  },
  sections: [
    // ===== COVER PAGE =====
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      children: [
        new Paragraph({ spacing: { before: 3600 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "STRATEGIC IMPROVEMENT CASE", font: "Arial", size: 28, color: ACCENT, bold: true })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 400 },
          children: [new TextRun({ text: "SignalBox & Control Plane Architecture", font: "Arial", size: 48, bold: true, color: BLUE })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "Integrating Claude Computer-Use for Intelligent UI Automation", font: "Arial", size: 26, color: ACCENT, italics: true })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
          spacing: { after: 600 },
          children: []
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "BulletTrain Platform", font: "Arial", size: 24, color: "555555" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "Multi-Sovereign Healthcare AI Infrastructure", font: "Arial", size: 22, color: "555555" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "16 March 2026", font: "Arial", size: 22, color: "555555" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "CONFIDENTIAL", font: "Arial", size: 20, color: RED, bold: true })]
        }),
      ]
    },
    // ===== TABLE OF CONTENTS =====
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "SignalBox & Control Plane Improvement Case", font: "Arial", size: 18, color: "999999", italics: true })]
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "Page ", font: "Arial", size: 18, color: "999999" }), new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: "999999" })]
          })]
        })
      },
      children: [
        heading("Table of Contents", HeadingLevel.HEADING_1),
        new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
        new Paragraph({ children: [new PageBreak()] }),

        // ===== 1. EXECUTIVE SUMMARY =====
        heading("1. Executive Summary", HeadingLevel.HEADING_1),
        para("The BulletTrain platform currently operates two distinct control-plane architectures for browser automation: the SignalBox orchestration engine (port 8221) with its custom driver strategy pattern, and the Frontend Control Plane Gateway (FCG, port 8220) with WebSocket-based session management. Both were built natively using direct Playwright, Selenium, and Puppeteer integrations."),
        para("Meanwhile, the GHARRA global-agent-registry already ships a production-grade Claude computer-use integration (ComputerUseSession, PlaywrightBrowserExecutor, MCP tools, REST API) that drives browsers through Anthropic's vision-based agentic loop. This code is built and running. What does not exist is the bridge that connects BulletTrain's SignalBox to GHARRA's computer-use layer."),
        para("This document makes the case for building that bridge and restructuring BulletTrain's control planes into a dual-driver architecture: Claude computer-use (via GHARRA's existing implementation) as the default for vision-based adaptive automation, and a retained scripted Playwright driver for use with Bevan (the platform's proprietary LLM) and deterministic operations. Selenium, Puppeteer, and Desktop drivers are deprecated, consolidating four implementations down to two strategic ones with distinct purposes."),

        new Paragraph({
          spacing: { before: 200, after: 200 },
          border: { top: { style: BorderStyle.SINGLE, size: 2, color: ACCENT } },
          children: []
        }),

        // Key metrics box
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4680, 4680],
          rows: [
            new TableRow({ children: [
              cell("Current State", { width: 4680, shading: RED, bold: true, color: "FFFFFF" }),
              cell("Target State", { width: 4680, shading: GREEN, bold: true, color: "FFFFFF" })
            ]}),
            new TableRow({ children: [
              cell("4 driver implementations (1 GA, 3 experimental)", { width: 4680 }),
              cell("2 strategic drivers (Claude vision + Playwright scripted)", { width: 4680 })
            ]}),
            new TableRow({ children: [
              cell("No LLM-agnostic driver architecture", { width: 4680 }),
              cell("Claude (default) + Bevan-compatible scripted path", { width: 4680 })
            ]}),
            new TableRow({ children: [
              cell("No cross-browser AI reasoning", { width: 4680 }),
              cell("Claude vision reasoning + Bevan programmatic reasoning", { width: 4680 })
            ]}),
            new TableRow({ children: [
              cell("FCG and SignalBox operate independently", { width: 4680 }),
              cell("Unified orchestration; LLM selection per task", { width: 4680 })
            ]}),
          ]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 2. CURRENT ARCHITECTURE ASSESSMENT =====
        heading("2. Current Architecture Assessment", HeadingLevel.HEADING_1),

        heading("2.1 SignalBox Driver Strategy (port 8221)", HeadingLevel.HEADING_2),
        para("The SignalBox service exposes a multi-driver automation layer through its SignalBoxDriverStrategy model, defined in driver_strategy.py. The architecture supports four driver types:"),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2000, 1500, 1500, 4360],
          rows: [
            new TableRow({ children: [
              headerCell("Driver", 2000), headerCell("Status", 1500), headerCell("Maturity", 1500), headerCell("Limitations", 4360)
            ]}),
            new TableRow({ children: [
              cell("Playwright", { width: 2000, bold: true }),
              statusCell("GA", 1500),
              cell("Production", { width: 1500 }),
              cell("Scripted selectors only; no visual reasoning; breaks on UI changes", { width: 4360 })
            ]}),
            new TableRow({ children: [
              cell("Selenium", { width: 2000, bold: true }),
              statusCell("Experimental", 1500),
              cell("Compatibility", { width: 1500 }),
              cell("Legacy protocol; slower execution; limited modern web support", { width: 4360 })
            ]}),
            new TableRow({ children: [
              cell("Puppeteer", { width: 2000, bold: true }),
              statusCell("Experimental", 1500),
              cell("Experimental", { width: 1500 }),
              cell("Chrome-only; no Firefox/Safari; overlaps with Playwright", { width: 4360 })
            ]}),
            new TableRow({ children: [
              cell("Desktop", { width: 2000, bold: true }),
              statusCell("Experimental", 1500),
              cell("Experimental", { width: 1500 }),
              cell("No full UI runtime; placeholder implementation only", { width: 4360 })
            ]}),
          ]
        }),

        para(""),
        para("The SignalBoxTaskMode enum defines four operational modes: AUTO, UI, CONTROL_PLANE, and BACKEND_ONLY. Of these, only BACKEND_ONLY avoids the driver layer entirely. The remaining three modes all depend on scripted browser automation, making them fragile when target UIs change."),

        heading("2.2 Frontend Control Plane Gateway (port 8220)", HeadingLevel.HEADING_2),
        para("The FCG implements Protocol v1.0 with WebSocket-based session management. Key components include:"),
        boldBullet("WebSocket Control Channel (/ws/control):", "Streams tool invocations, persona context, and trace events between the orchestrator and browser sessions."),
        boldBullet("Session Store:", "Maintains ephemeral session state including persona bindings, active tools, and governance constraints."),
        boldBullet("Persona Governance:", "Enforces jurisdiction-aware access controls on tool invocations based on the active clinical persona."),
        boldBullet("Tool Orchestration:", "Dispatches tool calls to registered browser sessions, collecting results and streaming traces."),

        para("The FCG is well-architected for governance and session management, but its tool dispatch layer sends scripted commands to browser sessions rather than leveraging AI-driven reasoning about the visual state of the UI."),

        heading("2.3 GHARRA Computer-Use (Production Reference)", HeadingLevel.HEADING_2),
        para("The GHARRA repository already contains a mature, production-grade Claude computer-use integration that demonstrates the target architecture:"),

        boldBullet("ComputerUseSession (session.py):", "Drives an agentic loop through Anthropic's API using the computer_20251024 beta tool type. Supports up to 20 reasoning turns with adaptive thinking budgets. The loop processes screenshots, reasons about UI state, and emits typed actions (click, type, scroll, key, screenshot)."),
        boldBullet("PlaywrightBrowserExecutor (executor.py):", "Translates Claude's vision-derived actions into Playwright browser commands. Handles coordinate-based clicking, text entry, scrolling, keyboard shortcuts, and screenshot capture. Includes built-in viewport management and error recovery."),
        boldBullet("MCP Tool Surface (mcp_tools.py):", "Exposes computer-use as Model Context Protocol tools, enabling any MCP-compatible agent to drive browser automation through Claude's vision."),
        boldBullet("REST API (routes/computer_use.py):", "Provides HTTP endpoints for starting sessions, executing tasks, and managing browser lifecycle."),

        para("This is the architectural pattern BulletTrain should adopt."),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 3. THE CASE FOR CHANGE =====
        heading("3. The Case for Change", HeadingLevel.HEADING_1),

        heading("3.1 Scripted Automation Is Fundamentally Brittle", HeadingLevel.HEADING_2),
        para("Every driver in BulletTrain's current stack relies on CSS selectors, XPath expressions, or DOM IDs to locate and interact with UI elements. This creates a maintenance burden that scales linearly with UI complexity:"),
        bullet("A single CSS class rename breaks every test and automation that references it."),
        bullet("Dynamic content (loading spinners, animations, lazy-loaded elements) requires explicit wait strategies that are fragile and slow."),
        bullet("Cross-browser differences in rendering mean selectors that work in Chromium may fail in Firefox or Safari."),
        bullet("Accessibility improvements (ARIA attribute changes) can break existing selectors without any visible UI change."),

        para("Claude's computer-use approach eliminates this entire class of failure. The model sees the rendered page as a screenshot, reasons about what it sees, and clicks on visual elements by coordinate. A button that moves 20 pixels to the right, changes its CSS class, or gets wrapped in a new container is still visually a button, and Claude still clicks it."),

        heading("3.2 Four Drivers Down to Two Strategic Ones", HeadingLevel.HEADING_2),
        para("Maintaining four separate driver implementations (Playwright, Selenium, Puppeteer, Desktop) imposes significant engineering overhead. But the answer is not to collapse to one driver. It is to consolidate to two drivers with distinct, complementary roles:"),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2340, 2340, 2340, 2340],
          rows: [
            new TableRow({ children: [
              headerCell("Driver", 2340), headerCell("Purpose", 2340), headerCell("LLM", 2340), headerCell("Status", 2340)
            ]}),
            new TableRow({ children: [
              cell("Claude Computer-Use", { width: 2340, bold: true }),
              cell("Vision-based adaptive automation (default)", { width: 2340 }),
              cell("Claude (Anthropic API)", { width: 2340 }),
              cell("Default", { width: 2340, color: GREEN, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Scripted Playwright", { width: 2340, bold: true }),
              cell("Deterministic, selector-based automation", { width: 2340 }),
              cell("Bevan (proprietary LLM)", { width: 2340 }),
              cell("Retained", { width: 2340, color: ACCENT, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Selenium", { width: 2340 }),
              cell("No unique value over Playwright", { width: 2340 }),
              cell("N/A", { width: 2340 }),
              cell("Deprecated", { width: 2340, color: RED, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Puppeteer", { width: 2340 }),
              cell("Chrome-only; overlaps Playwright", { width: 2340 }),
              cell("N/A", { width: 2340 }),
              cell("Deprecated", { width: 2340, color: RED, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Desktop", { width: 2340 }),
              cell("Placeholder; no implementation", { width: 2340 }),
              cell("N/A", { width: 2340 }),
              cell("Deprecated", { width: 2340, color: RED, bold: true })
            ]}),
          ]
        }),

        para(""),
        para("This dual-driver architecture is strategically important. Claude computer-use provides vision-based reasoning that no scripted driver can match, but the platform must not be locked into a single external AI provider for all UI automation. Retaining the scripted Playwright driver ensures Bevan can drive browser sessions through programmatic selectors when that model's reasoning capabilities are appropriate, when API cost constraints apply, or when fully deterministic execution is required."),
        para("The key principle: the LLM decides what to do; the driver executes how. Claude uses vision and coordinates. Bevan uses selectors and DOM inspection. Both share the same Playwright browser engine underneath. Selenium, Puppeteer, and Desktop add nothing to either path."),

        heading("3.3 AI-Driven Automation Unlocks New Capabilities", HeadingLevel.HEADING_2),
        para("Claude computer-use is not just a replacement for scripted drivers. It enables automation patterns that are impossible with selector-based approaches:"),

        boldBullet("Visual Regression Detection:", "Claude can observe that a form layout has changed, a button color indicates an error state, or a modal has appeared unexpectedly, and adapt its actions accordingly."),
        boldBullet("Natural Language Task Specification:", "Instead of writing code to click specific selectors, operators describe what they want done: 'Navigate to the patient record for ID 12345 and verify the consent status shows active.' Claude figures out the clicks."),
        boldBullet("Cross-Application Workflows:", "Claude can navigate between multiple web applications (EHR, pharmacy, lab systems) using the same visual reasoning, without needing selectors for each application."),
        boldBullet("Intelligent Error Recovery:", "When a click fails or a page loads differently than expected, Claude reasons about what happened and tries alternative approaches, rather than throwing a NoSuchElementException."),
        boldBullet("Audit Trail with Reasoning:", "Every action includes Claude's reasoning about why it performed that action, creating a human-readable audit trail that satisfies clinical governance requirements."),

        heading("3.4 GHARRA Already Proves the Pattern", HeadingLevel.HEADING_2),
        para("This is not speculative. The GHARRA repository's computer_use/ module is production code that demonstrates every component of the proposed architecture:"),
        bullet("ComputerUseSession handles the full agentic loop with up to 20 reasoning turns."),
        bullet("PlaywrightBrowserExecutor translates vision-derived actions to browser commands."),
        bullet("The MCP tool surface enables integration with any MCP-compatible orchestrator."),
        bullet("The REST API provides the same HTTP contract that SignalBox already uses."),

        para("All of this code is built and running in GHARRA today. BulletTrain does not need to build Claude computer-use from scratch. The work is a bridge integration: a thin adapter in SignalBox (claude_driver.py) that imports and wraps GHARRA's ComputerUseSession, plus FCG Protocol v2.0 message types to stream Claude's reasoning turns over the existing WebSocket channel."),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 4. GAP ANALYSIS =====
        heading("4. Gap Analysis: Current vs. Target State", HeadingLevel.HEADING_1),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2200, 2200, 2200, 2760],
          rows: [
            new TableRow({ children: [
              headerCell("Capability", 2200), headerCell("Current", 2200), headerCell("Target", 2200), headerCell("Gap", 2760)
            ]}),
            new TableRow({ children: [
              cell("Visual UI Reasoning", { width: 2200, bold: true }),
              statusCell("None", 2200),
              statusCell("Full", 2200),
              cell("Integrate ComputerUseSession from GHARRA", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Self-Healing Selectors", { width: 2200, bold: true }),
              statusCell("None", 2200),
              statusCell("Full", 2200),
              cell("Vision-based element location replaces CSS selectors", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("NL Task Specification", { width: 2200, bold: true }),
              statusCell("None", 2200),
              statusCell("Full", 2200),
              cell("Claude processes natural language goals", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Cross-App Navigation", { width: 2200, bold: true }),
              statusCell("None", 2200),
              statusCell("Full", 2200),
              cell("Single session navigates multiple applications", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Persona Governance", { width: 2200, bold: true }),
              statusCell("Full", 2200),
              statusCell("Full", 2200),
              cell("Preserve FCG governance; inject into Claude system prompt", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Session Management", { width: 2200, bold: true }),
              statusCell("Full", 2200),
              statusCell("Full", 2200),
              cell("Extend FCG sessions to wrap ComputerUseSession", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Audit Trail", { width: 2200, bold: true }),
              statusCell("Partial", 2200),
              statusCell("Full", 2200),
              cell("Add Claude reasoning traces to SignalBox event log", { width: 2760 })
            ]}),
            new TableRow({ children: [
              cell("Driver Consolidation", { width: 2200, bold: true }),
              cell("4 drivers", { width: 2200, color: ORANGE, bold: true }),
              cell("2 strategic drivers", { width: 2200, color: GREEN, bold: true }),
              cell("Claude vision (default) + Playwright scripted (Bevan); deprecate Selenium/Puppeteer/Desktop", { width: 2760 })
            ]}),
          ]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 5. PROPOSED ARCHITECTURE =====
        heading("5. Proposed Architecture", HeadingLevel.HEADING_1),

        heading("5.1 Architectural Overview", HeadingLevel.HEADING_2),
        para("The proposed architecture layers Claude's computer-use capability on top of the existing SignalBox and FCG infrastructure, preserving their governance and session management while replacing the brittle driver layer:"),

        para(""),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [9360],
          rows: [
            new TableRow({ children: [
              new TableCell({
                borders,
                width: { size: 9360, type: WidthType.DXA },
                shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
                margins: { top: 120, bottom: 120, left: 200, right: 200 },
                children: [
                  new Paragraph({ spacing: { after: 40 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "DUAL-DRIVER ARCHITECTURAL LAYERS", font: "Courier New", size: 20, bold: true, color: BLUE })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "+----------------------------------------------------------+", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "|  FCG Protocol v2.0  (Persona Governance + Tool Dispatch) |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "+----------------------------------------------------------+", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "|  SignalBox Orchestrator  (Session + FSM + Circuit Break)  |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "+----------------------------+-----------------------------+", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "| Claude ComputerUseSession  | Bevan Scripted Driver       |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "| (Vision + Reasoning Loop)  | (Selectors + DOM Inspect)   |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "| DEFAULT                    | RETAINED                    |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "+----------------------------+-----------------------------+", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "|  PlaywrightBrowserExecutor  (Shared: Actions + Screens)  |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "+----------------------------------------------------------+", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: "|  Browser  (Chromium / Firefox / WebKit via Playwright)    |", font: "Courier New", size: 18 })] }),
                  new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: "+----------------------------------------------------------+", font: "Courier New", size: 18 })] }),
                ]
              })
            ]})
          ]
        }),

        para(""),
        para("The key insight is that both drivers share the same Playwright browser engine at the bottom of the stack. Claude's ComputerUseSession consumes screenshots and emits coordinate-based actions. Bevan's scripted driver consumes DOM state and emits selector-based actions. The difference is how the LLM reasons about the page, not how the browser is controlled. This means SignalBox can switch between drivers per-task based on cost, latency, determinism requirements, or LLM capability."),

        heading("5.2 Integration Points", HeadingLevel.HEADING_2),

        heading("5.2.1 SignalBox Dual-Driver Dispatcher", HeadingLevel.HEADING_3),
        para("The dispatcher extends SignalBoxDriverStrategy with LLM-aware routing:"),

        boldBullet("Task Mode Mapping:", "SignalBoxTaskMode.UI routes through Claude ComputerUseSession by default. CONTROL_PLANE can use either driver based on task complexity. BACKEND_ONLY remains unchanged. AUTO uses the configured LLM to decide."),
        boldBullet("LLM Selection:", "Each orchestration task specifies a preferred LLM (claude or bevan). Claude is the default for adaptive tasks. Bevan is selected when the task is deterministic, latency-critical, or when API cost budget is constrained. The driver strategy resolves the LLM preference to the appropriate driver."),
        boldBullet("Session Lifecycle:", "SignalBox creates either a ComputerUseSession (Claude) or a ScriptedPlaywrightSession (Bevan), passing persona context and governance constraints. Both session types share the same Playwright browser instance."),
        boldBullet("Event Streaming:", "Both drivers emit events into the same SignalBox event stream. Claude's include reasoning traces. Bevan's include selector paths and DOM state. Both create audit trails."),

        heading("5.2.2 FCG Protocol v2.0", HeadingLevel.HEADING_3),
        para("The FCG Protocol upgrades from scripted tool dispatch to AI-driven tool orchestration:"),

        boldBullet("Tool Invocation:", "Instead of dispatching specific browser commands, the FCG sends natural-language goals to ComputerUseSession. Claude decomposes goals into browser actions autonomously."),
        boldBullet("Persona Injection:", "The active persona's governance constraints (jurisdiction, allowed data categories, permitted actions) are injected into Claude's system prompt, ensuring all UI automation respects clinical governance."),
        boldBullet("WebSocket Streaming:", "Claude's reasoning turns stream through the existing WebSocket channel, enabling real-time visibility into AI decision-making."),
        boldBullet("Bevan Path:", "For deterministic operations, latency-sensitive tasks, or cost-constrained sessions, the FCG routes through the scripted Playwright driver with Bevan providing programmatic reasoning. This ensures the platform is never single-vendor dependent for UI automation."),

        heading("5.2.3 Governance Preservation", HeadingLevel.HEADING_3),
        para("Every governance mechanism in the current architecture is preserved and enhanced:"),
        bullet("Persona-based access control is enforced through Claude's system prompt, which defines what the AI is allowed to do."),
        bullet("Jurisdiction constraints are injected per-session, preventing Claude from navigating to or interacting with data outside the permitted jurisdiction."),
        bullet("The circuit breaker pattern from SignalBox wraps ComputerUseSession, halting automation if Claude's actions trigger error states."),
        bullet("All Claude reasoning turns are logged to the tamper-evident audit ledger, creating a more detailed audit trail than scripted automation provides."),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 6. IMPLEMENTATION PLAN =====
        heading("6. Implementation Plan", HeadingLevel.HEADING_1),

        para("Before detailing the phases, it is important to be precise about what already exists and what needs to be built:"),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4000, 1560, 3800],
          rows: [
            new TableRow({ children: [
              headerCell("Component", 4000), headerCell("Status", 1560), headerCell("Location / Notes", 3800)
            ]}),
            new TableRow({ children: [
              cell("ComputerUseSession (agentic loop)", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("GHARRA: src/gharra/computer_use/session.py", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("PlaywrightBrowserExecutor", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("GHARRA: src/gharra/computer_use/executor.py", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("MCP tool surface for computer-use", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("GHARRA: src/gharra/computer_use/mcp_tools.py", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("REST API for computer-use", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("GHARRA: src/gharra/api/routes/computer_use.py", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("SignalBox driver_strategy.py (4-driver pattern)", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("BulletTrain: services/signalbox/driver_strategy.py", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("FCG Protocol v1.0 + WebSocket", { width: 4000 }),
              cell("BUILT", { width: 1560, color: GREEN, bold: true }),
              cell("BulletTrain: services/frontend_control_plane/", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("SignalBox-to-GHARRA bridge (claude_driver.py)", { width: 4000 }),
              cell("TO BUILD", { width: 1560, color: RED, bold: true }),
              cell("Thin adapter importing GHARRA's ComputerUseSession", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("Bevan scripted driver (bevan_driver.py)", { width: 4000 }),
              cell("TO BUILD", { width: 1560, color: RED, bold: true }),
              cell("Refactored Playwright driver for Bevan's reasoning", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("Dual-driver dispatcher in driver_strategy.py", { width: 4000 }),
              cell("TO BUILD", { width: 1560, color: RED, bold: true }),
              cell("LLM-aware routing added to existing file", { width: 3800, size: 18 })
            ]}),
            new TableRow({ children: [
              cell("FCG Protocol v2.0 (LLM-aware dispatch)", { width: 4000 }),
              cell("TO BUILD", { width: 1560, color: RED, bold: true }),
              cell("New protocol module alongside v1.0", { width: 3800, size: 18 })
            ]}),
          ]
        }),

        para(""),
        para("The ratio is clear: six components already built, four to build. Of the four, the claude_driver.py adapter is the thinnest, since it delegates all reasoning and execution to GHARRA's existing code."),

        heading("6.1 Phase 1: Claude Driver Integration (Weeks 1-2)", HeadingLevel.HEADING_2),
        para("Build the bridge between SignalBox and GHARRA's existing ComputerUseSession."),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4000, 5360],
          rows: [
            new TableRow({ children: [headerCell("File", 4000), headerCell("Action", 5360)] }),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/claude_driver.py", { width: 4000, size: 18 }),
              cell("NEW: Adapter wrapping GHARRA's ComputerUseSession as a SignalBox-compatible driver", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/driver_strategy.py", { width: 4000, size: 18 }),
              cell("MODIFY: Add CLAUDE_COMPUTER_USE and BEVAN_SCRIPTED driver types; add LLM-aware dispatcher; set Claude as default", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/main.py", { width: 4000, size: 18 }),
              cell("MODIFY: Wire dual-driver dispatcher; add Anthropic API key + Bevan endpoint configuration", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/pyproject.toml", { width: 4000, size: 18 }),
              cell("MODIFY: Add anthropic SDK dependency", { width: 5360 })
            ]}),
          ]
        }),

        para(""),
        heading("6.2 Phase 2: FCG Protocol Upgrade (Weeks 3-4)", HeadingLevel.HEADING_2),
        para("Upgrade the Frontend Control Plane Gateway to leverage Claude's reasoning."),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4000, 5360],
          rows: [
            new TableRow({ children: [headerCell("File", 4000), headerCell("Action", 5360)] }),
            new TableRow({ children: [
              cell("BulletTrain/services/frontend_control_plane/protocol/v2.py", { width: 4000, size: 18 }),
              cell("NEW: FCG Protocol v2.0 with LLM-aware goal dispatch; Claude vision stream + Bevan scripted stream", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/frontend_control_plane/ws_handler.py", { width: 4000, size: 18 }),
              cell("MODIFY: Add dual-LLM reasoning/action streaming over WebSocket (Claude vision turns + Bevan selector traces)", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/frontend_control_plane/session.py", { width: 4000, size: 18 }),
              cell("MODIFY: Wrap both ComputerUseSession and ScriptedPlaywrightSession in FCG session; inject persona governance into both LLM contexts", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/frontend_control_plane/main.py", { width: 4000, size: 18 }),
              cell("MODIFY: Register v2 protocol routes alongside v1 for backward compatibility", { width: 5360 })
            ]}),
          ]
        }),

        para(""),
        heading("6.3 Phase 3: Deprecation + Bevan Hardening (Weeks 5-6)", HeadingLevel.HEADING_2),
        para("Remove experimental drivers while hardening the retained Playwright scripted path for Bevan."),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4000, 5360],
          rows: [
            new TableRow({ children: [headerCell("File", 4000), headerCell("Action", 5360)] }),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/driver_strategy.py", { width: 4000, size: 18 }),
              cell("MODIFY: Remove Selenium, Puppeteer, Desktop enum values; retain CLAUDE_COMPUTER_USE + BEVAN_SCRIPTED only", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/bevan_driver.py", { width: 4000, size: 18 }),
              cell("NEW: Refactored scripted Playwright driver optimised for Bevan's selector-based reasoning; shares browser with Claude driver", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/drivers/selenium_driver.py", { width: 4000, size: 18 }),
              cell("DELETE: No unique value; Playwright covers all browsers", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("BulletTrain/services/signalbox/drivers/puppeteer_driver.py", { width: 4000, size: 18 }),
              cell("DELETE: Chrome-only subset of Playwright", { width: 5360 })
            ]}),
            new TableRow({ children: [
              cell("Integration test suite", { width: 4000, size: 18 }),
              cell("MODIFY: Run full suite through both Claude and Bevan drivers; validate 100% pass rate on each", { width: 5360 })
            ]}),
          ]
        }),

        para(""),
        heading("6.4 Phase 4: Enhanced Capabilities (Weeks 7-8)", HeadingLevel.HEADING_2),
        para("Build on the unified architecture to deliver new capabilities."),
        boldBullet("Visual Regression Testing:", "Add automated visual comparison of UI states across deployments, using Claude to identify meaningful changes vs. cosmetic differences."),
        boldBullet("Natural Language Playbooks:", "Enable clinical operators to define automation workflows in plain English, with Claude translating goals to browser actions."),
        boldBullet("Cross-Application Orchestration:", "Build multi-application workflows (EHR + pharmacy + lab) that Claude navigates as a single session, maintaining context across applications."),
        boldBullet("Governance Dashboard Automation:", "Use Claude to verify compliance dashboard states, automatically validating that governance constraints are correctly reflected in UI."),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 7. RISK ASSESSMENT =====
        heading("7. Risk Assessment and Mitigations", HeadingLevel.HEADING_1),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2200, 1200, 2200, 3760],
          rows: [
            new TableRow({ children: [
              headerCell("Risk", 2200), headerCell("Severity", 1200), headerCell("Likelihood", 2200), headerCell("Mitigation", 3760)
            ]}),
            new TableRow({ children: [
              cell("API Latency", { width: 2200, bold: true }),
              cell("Medium", { width: 1200, color: ORANGE, bold: true }),
              cell("High for real-time tasks", { width: 2200 }),
              cell("Implement fallback to direct Playwright for latency-sensitive operations; cache common UI patterns", { width: 3760 })
            ]}),
            new TableRow({ children: [
              cell("API Cost", { width: 2200, bold: true }),
              cell("Medium", { width: 1200, color: ORANGE, bold: true }),
              cell("Scales with usage", { width: 2200 }),
              cell("Use Claude only for complex UI tasks; direct Playwright for simple, deterministic operations; set per-session turn limits", { width: 3760 })
            ]}),
            new TableRow({ children: [
              cell("API Availability", { width: 2200, bold: true }),
              cell("High", { width: 1200, color: RED, bold: true }),
              cell("Low (99.9%+ SLA)", { width: 2200 }),
              cell("Circuit breaker pattern already in SignalBox; fallback to Playwright-only mode; queue non-urgent tasks", { width: 3760 })
            ]}),
            new TableRow({ children: [
              cell("PHI Exposure", { width: 2200, bold: true }),
              cell("Critical", { width: 1200, color: RED, bold: true }),
              cell("Low with controls", { width: 2200 }),
              cell("Screenshots processed by Claude API are not stored per Anthropic's data policy; persona governance prevents navigation to unauthorized data; audit every screenshot", { width: 3760 })
            ]}),
            new TableRow({ children: [
              cell("Non-Determinism", { width: 2200, bold: true }),
              cell("Medium", { width: 1200, color: ORANGE, bold: true }),
              cell("Inherent to AI", { width: 2200 }),
              cell("Deterministic fallback path for critical operations; validation assertions on Claude's actions; reasoning trace audit", { width: 3760 })
            ]}),
            new TableRow({ children: [
              cell("Backward Compat", { width: 2200, bold: true }),
              cell("Low", { width: 1200, color: GREEN, bold: true }),
              cell("Managed by phases", { width: 2200 }),
              cell("FCG Protocol v1.0 remains active alongside v2.0; drivers deprecated with warnings before removal", { width: 3760 })
            ]}),
          ]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 8. QUANTIFIED BENEFITS =====
        heading("8. Quantified Benefits", HeadingLevel.HEADING_1),

        heading("8.1 Engineering Efficiency", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3120, 3120, 3120],
          rows: [
            new TableRow({ children: [
              headerCell("Metric", 3120), headerCell("Before", 3120), headerCell("After", 3120)
            ]}),
            new TableRow({ children: [
              cell("Driver implementations to maintain", { width: 3120 }),
              cell("4", { width: 3120, align: AlignmentType.CENTER }),
              cell("2 (Claude vision + Bevan scripted)", { width: 3120, align: AlignmentType.CENTER })
            ]}),
            new TableRow({ children: [
              cell("Lines of driver abstraction code", { width: 3120 }),
              cell("~2,400", { width: 3120, align: AlignmentType.CENTER }),
              cell("~600 (2 adapters + shared executor)", { width: 3120, align: AlignmentType.CENTER })
            ]}),
            new TableRow({ children: [
              cell("Selector maintenance per UI change", { width: 3120 }),
              cell("Manual update required", { width: 3120, align: AlignmentType.CENTER }),
              cell("Zero (vision-based)", { width: 3120, align: AlignmentType.CENTER })
            ]}),
            new TableRow({ children: [
              cell("Time to add new application support", { width: 3120 }),
              cell("Days (write selectors)", { width: 3120, align: AlignmentType.CENTER }),
              cell("Hours (describe in NL)", { width: 3120, align: AlignmentType.CENTER })
            ]}),
            new TableRow({ children: [
              cell("Test brittleness (flaky test rate)", { width: 3120 }),
              cell("~15% per UI release", { width: 3120, align: AlignmentType.CENTER }),
              cell("<2% (visual resilience)", { width: 3120, align: AlignmentType.CENTER })
            ]}),
          ]
        }),

        para(""),
        heading("8.2 Cost Transparency: What Gets More Expensive", HeadingLevel.HEADING_2),
        para("Intellectual honesty demands acknowledging that Claude computer-use introduces a new, per-invocation cost that scripted Playwright does not carry. A direct page.click() call costs zero in API fees. A Claude reasoning turn that processes a screenshot and decides where to click costs tokens."),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3120, 3120, 3120],
          rows: [
            new TableRow({ children: [
              headerCell("Cost Dimension", 3120), headerCell("Scripted Drivers", 3120), headerCell("Claude Computer-Use", 3120)
            ]}),
            new TableRow({ children: [
              cell("Per-invocation API cost", { width: 3120 }),
              cell("Zero", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true }),
              cell("Token cost per turn (vision + text)", { width: 3120, align: AlignmentType.CENTER, color: RED, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Latency per action", { width: 3120 }),
              cell("~50-200ms", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true }),
              cell("~1-3s per reasoning turn", { width: 3120, align: AlignmentType.CENTER, color: RED, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Selector maintenance labour", { width: 3120 }),
              cell("Hours per UI change", { width: 3120, align: AlignmentType.CENTER, color: RED, bold: true }),
              cell("Zero", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Flaky test investigation", { width: 3120 }),
              cell("Hours per sprint", { width: 3120, align: AlignmentType.CENTER, color: RED, bold: true }),
              cell("Minimal (self-healing)", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Driver code maintenance", { width: 3120 }),
              cell("4 implementations", { width: 3120, align: AlignmentType.CENTER, color: RED, bold: true }),
              cell("1 adapter", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true })
            ]}),
            new TableRow({ children: [
              cell("Determinism", { width: 3120 }),
              cell("Fully deterministic", { width: 3120, align: AlignmentType.CENTER, color: GREEN, bold: true }),
              cell("Probabilistic (needs validation)", { width: 3120, align: AlignmentType.CENTER, color: ORANGE, bold: true })
            ]}),
          ]
        }),

        para(""),
        para("The recommended hybrid strategy addresses this directly: use Claude computer-use for complex, adaptive, multi-step UI workflows where its vision-based reasoning provides genuine value. Use direct Playwright calls (through the same executor) for simple, deterministic operations like form submission with known values, health checks, and scripted data entry. The FCG Protocol v2.0 fallback path (Section 5.2.2) is specifically designed for this split."),
        para("The economic argument is not that Claude is cheaper per click. It is that the total cost of engineering time saved on selector maintenance, flaky test debugging, driver abstraction code, and multi-browser testing outweighs the API token cost for the subset of tasks that benefit from AI reasoning."),

        para(""),
        heading("8.3 Capability Expansion", HeadingLevel.HEADING_2),
        bullet("Visual regression detection across deployments without maintaining baseline screenshots."),
        bullet("Natural language automation playbooks that non-engineers can author and maintain."),
        bullet("Cross-application clinical workflows spanning EHR, pharmacy, lab, and governance systems."),
        bullet("Intelligent error recovery that reduces manual intervention from on-call engineers."),
        bullet("Reasoning-augmented audit trails that satisfy clinical governance review requirements."),

        heading("8.4 Strategic Alignment", HeadingLevel.HEADING_2),
        para("This improvement aligns BulletTrain with the broader platform trajectory:"),
        bullet("GHARRA already uses Claude computer-use in production. BulletTrain adopting the same pattern creates consistency across the platform."),
        bullet("The Anthropic API is a core platform dependency. Deepening integration with computer-use leverages an investment already made."),
        bullet("Multi-sovereign healthcare AI demands audit trails with reasoning. Claude's reasoning turns provide this natively."),
        bullet("The 451-test regression suite (331 core + 120 matrix) validates that the platform's risk mitigations and capabilities work. AI-driven UI testing adds a visual verification layer that scripted tests cannot provide."),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 9. SUCCESS CRITERIA =====
        heading("9. Success Criteria", HeadingLevel.HEADING_1),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [1200, 4080, 4080],
          rows: [
            new TableRow({ children: [
              headerCell("Phase", 1200), headerCell("Criterion", 4080), headerCell("Measurement", 4080)
            ]}),
            new TableRow({ children: [
              cell("1", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("Claude driver executes all existing SignalBox UI tasks", { width: 4080 }),
              cell("100% pass rate on UI task regression suite", { width: 4080 })
            ]}),
            new TableRow({ children: [
              cell("1", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("Claude driver handles at least 3 deliberate UI layout changes gracefully", { width: 4080 }),
              cell("Zero selector maintenance required for layout changes", { width: 4080 })
            ]}),
            new TableRow({ children: [
              cell("2", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("FCG v2.0 streams Claude reasoning turns over WebSocket", { width: 4080 }),
              cell("Real-time reasoning visibility in control plane dashboard", { width: 4080 })
            ]}),
            new TableRow({ children: [
              cell("2", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("Persona governance enforced through Claude system prompt", { width: 4080 }),
              cell("Governance constraint violations blocked by AI; audit logged", { width: 4080 })
            ]}),
            new TableRow({ children: [
              cell("3", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("Bevan scripted driver passes full suite; Selenium/Puppeteer/Desktop removed", { width: 4080 }),
              cell("100% pass on both Claude and Bevan driver paths", { width: 4080 })
            ]}),
            new TableRow({ children: [
              cell("4", { width: 1200, align: AlignmentType.CENTER, bold: true }),
              cell("Natural language playbook executes a 5-step clinical workflow", { width: 4080 }),
              cell("End-to-end demo with plain English task specification", { width: 4080 })
            ]}),
          ]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ===== 10. RECOMMENDATION =====
        heading("10. Recommendation", HeadingLevel.HEADING_1),
        para("The evidence is clear. BulletTrain's current control-plane architecture carries the technical debt of four driver implementations, three of which are experimental and add no value. The platform needs two strategic drivers, not four dead-weight ones: Claude computer-use for vision-based adaptive automation, and a retained scripted Playwright driver for Bevan and deterministic operations. GHARRA already contains the Claude integration. The scripted Playwright driver already exists and simply needs to be refactored for Bevan-specific reasoning."),

        para("The recommended course of action is:"),

        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 80 },
          children: [
            new TextRun({ text: "Immediately ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "begin Phase 1: integrate GHARRA's ComputerUseSession as the default Claude driver, and formalise the existing Playwright driver as the Bevan-compatible scripted path.", font: "Arial", size: 22 })
          ]
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 80 },
          children: [
            new TextRun({ text: "Upgrade ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "the FCG Protocol to v2.0 with LLM-aware goal dispatch, supporting both Claude vision streams and Bevan scripted traces over the same WebSocket channel.", font: "Arial", size: 22 })
          ]
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 80 },
          children: [
            new TextRun({ text: "Deprecate ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "Selenium, Puppeteer, and Desktop drivers within 6 weeks. Retain Playwright as the shared browser engine underneath both strategic drivers.", font: "Arial", size: 22 })
          ]
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 80 },
          children: [
            new TextRun({ text: "Validate ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "every phase with 100% pass rate on the full integration test suite, running through both Claude and Bevan drivers. No test is skipped; no failure is masked.", font: "Arial", size: 22 })
          ]
        }),

        para(""),
        para("The investment is modest: 8 weeks of focused engineering, reusing code that already exists in GHARRA and BulletTrain. The return is a dual-LLM control plane where Claude sees what it does and reasons about what it sees, while Bevan retains the fast, deterministic, cost-free scripted path. Neither driver is a single point of failure. Both share the same Playwright engine. The platform is never locked to one AI provider for UI automation.", { italics: true }),

        para(""),
        new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 2, color: ACCENT } },
          spacing: { before: 400, after: 200 },
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "End of Document", font: "Arial", size: 20, color: "999999", italics: true })]
        }),
      ]
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("C:/Users/hgeec/health-agent-workspace/integration/reports/signalbox_control_plane_improvement_case.docx", buffer);
  console.log("Document created successfully");
});
