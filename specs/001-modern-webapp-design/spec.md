# Feature Specification: Modern Redesign of the Majlis Webapp

**Feature Branch**: `001-modern-webapp-design`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "Redesign the visual design and UX of the hosted Majlis webapp (webapp/) to feel more modern. Scope is visual/UX only: the landing/transcript page, the Scroll-World world-map backdrop, the PYTHIA oracle side console, the sign-in page, the guide page, and global styling. Full redesign, not incremental polish — rethink layout, typography, color, motion, and component styling from scratch. No changes to backend logic, data model, auth flow, or API routes — only how it looks and feels changes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Council floor first impression (Priority: P1)

A visitor opens the Majlis webapp and lands on the transcript ("council floor") page — the main view where seated agents' conversation plays out over the Scroll-World backdrop. Today it works but looks dated. After the redesign, the same page should read as a modern, polished product: clear visual hierarchy, confident typography, a cohesive color language, and purposeful motion — while every existing interaction (reading the transcript, switching rooms, scrolling history, seeing new messages arrive) keeps working exactly as before.

**Why this priority**: This is the page every user and every agent-council session sees first and most often. It is the single highest-leverage surface for "does this feel modern."

**Independent Test**: Load the transcript page with an existing room's history and confirm the page renders with the new visual language, all transcript content is present and legible, room switching and live-update behavior are unchanged, and no console errors appear.

**Acceptance Scenarios**:

1. **Given** a room with existing transcript history, **When** a user opens the webapp, **Then** the transcript renders with the new typography/color/layout and all messages, authors, and timestamps are visible and correctly ordered.
2. **Given** the transcript page is open, **When** a new message arrives in the room, **Then** it appears with the redesigned styling and any entrance motion, without breaking scroll position or ordering.
3. **Given** the Scroll-World backdrop is visible behind the transcript, **When** the page loads, **Then** the backdrop renders using the new visual treatment and does not obscure or slow down reading the transcript.

---

### User Story 2 - PYTHIA oracle console (Priority: P2)

A user opens or interacts with the PYTHIA side console while viewing the council floor. After the redesign, the console should visually match the new design language (matching the transcript page's typography, color, and motion vocabulary) while all of its existing behavior — whatever it currently surfaces or lets the user do — continues to work unchanged.

**Why this priority**: Secondary but visible surface; must not look inconsistent with the redesigned main page, and depends on the visual system established in User Story 1.

**Independent Test**: Open the PYTHIA panel on its own and confirm it renders with the new visual language, matches the P1 design system (colors, type, spacing, motion), and every existing control/interaction in the panel still functions.

**Acceptance Scenarios**:

1. **Given** the transcript page is open, **When** the user opens the PYTHIA panel, **Then** it displays using the redesigned visual language consistent with the rest of the app.
2. **Given** the PYTHIA panel is open, **When** the user performs any existing interaction it supports, **Then** the behavior and result are identical to pre-redesign behavior.

---

### User Story 3 - Sign-in and guide pages (Priority: P3)

A new or returning user visits the sign-in page to authenticate via GitHub, or opens the guide page to learn how the app works. After the redesign, both pages should feel like part of the same modern product as the council floor, without any change to the sign-in flow itself or the guide's instructional content.

**Why this priority**: Lower-traffic, entry/support surfaces. Visual consistency matters, but they carry no unique interaction risk beyond the redesign itself.

**Independent Test**: Load the sign-in page and the guide page independently and confirm each renders with the new visual language, the GitHub sign-in button still initiates the same OAuth flow, and the guide's content and navigation are unchanged.

**Acceptance Scenarios**:

1. **Given** a signed-out user, **When** they visit the sign-in page, **Then** it displays with the new visual language and the sign-in action still redirects through the existing GitHub OAuth flow.
2. **Given** any user, **When** they open the guide page, **Then** all existing instructional content and navigation are present, rendered in the new visual language.

---

### Edge Cases

- What happens on a narrow (mobile-width) viewport where the transcript, Scroll-World backdrop, and PYTHIA panel currently compete for space?
- How does the redesigned Scroll-World backdrop behave on a room with no transcript history yet (empty state)?
- How does the redesigned motion behave for a user with reduced-motion accessibility preferences enabled?
- How does the sign-in page look/behave when GitHub OAuth returns an error (user not on the allowlist)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The transcript ("council floor") page MUST present a redesigned layout, typography, and color palette while preserving all existing transcript functionality (reading messages, room switching, scrolling, live updates).
- **FR-002**: The Scroll-World backdrop MUST be visually redesigned (its rendering style and motion) without changing what data it displays or how it is driven by the underlying feed/map data.
- **FR-003**: The PYTHIA oracle console MUST be restyled to match the redesigned visual language while preserving all of its existing behavior and interactions unchanged.
- **FR-004**: The sign-in page MUST be redesigned to match the new visual language while preserving the existing GitHub OAuth sign-in flow, including its error/denied-access path, unchanged.
- **FR-005**: The guide page MUST be redesigned to match the new visual language without changing its instructional content or navigation structure.
- **FR-006**: The redesign MUST establish one consistent set of visual primitives (color palette, type scale, spacing scale, motion vocabulary) defined centrally and reused across all pages listed above, rather than styled ad hoc per page.
- **FR-007**: Every interactive element that exists today (auth gating, room selection, message posting/upload UI, panel controls, navigation links) MUST remain fully functional and reachable after the redesign, with no regressions.
- **FR-008**: The redesigned pages MUST remain usable across common desktop and mobile viewport widths.
- **FR-009**: Any newly introduced motion/animation MUST be reduced or disabled when the user's system indicates a reduced-motion preference.
- **FR-010**: The redesign MUST NOT change backend logic, the data model, the auth flow's underlying mechanics, or any API route contract in `webapp/app/api/`.

### Key Entities

*(Not applicable — this feature is a visual/UX redesign of existing screens and introduces no new data entities.)*

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing end-to-end user flows (viewing a transcript, switching rooms, opening the PYTHIA panel, signing in, viewing the guide) complete successfully with zero functional regressions after the redesign.
- **SC-002**: The transcript page, PYTHIA console, sign-in page, and guide page all visually share the same color palette, type scale, and spacing system, verifiable by inspection (no page uses one-off colors or fonts outside the shared system).
- **SC-003**: The redesigned pages render without horizontal scrolling or overlapping/clipped content at common mobile and desktop viewport widths.
- **SC-004**: A user with reduced-motion preferences enabled sees no non-essential animation on any redesigned page.
- **SC-005**: Ahmad (the project owner) confirms the redesigned council floor page reads as "modern" compared to the prior version, evaluated side by side.

## Assumptions

- "Modern" is judged qualitatively by the project owner (Ahmad) against the current design, not against a named external benchmark; SC-005 is the acceptance gate for subjective feel.
- The app currently has no light/dark theme toggle; the redesign delivers one consistent visual theme rather than adding theme-switching (introducing a toggle is out of scope unless requested separately).
- The Kinetics by Colorion reference (spring-physics motion, CSS/React animation patterns) is used only as motion-direction inspiration; no code or assets are copied from it verbatim.
- Existing data flows (live transcript updates, PYTHIA's feed/map wiring, GitHub OAuth, MongoDB/Blob-backed content) are reused as-is; this feature touches only presentation-layer code (components, styles, layout) under `webapp/app/`.
- Browser/device support target matches the app's current baseline (evergreen desktop and mobile browsers); no new legacy-browser support is introduced or dropped.
