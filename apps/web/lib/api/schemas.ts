import type { components } from "@decision-lab/contracts";

/**
 * Typed aliases over the generated canonical schemas. These are pure
 * re-exports of `@decision-lab/contracts`; Web/UX must not redefine any of
 * these shapes locally. New aliases may only be added when the underlying
 * component already exists in the generated surface.
 */
export type Schemas = components["schemas"];

// System
export type HealthResponse = Schemas["HealthResponse"];

// Identity / tenancy (frozen by Task 19A; routes pending backend implementation)
export type User = Schemas["User"];
export type UserSession = Schemas["UserSession"];
export type WorkspaceMembership = Schemas["WorkspaceMembership"];

// Source freeze provenance
export type PreRunSourceRecord = Schemas["PreRunSourceRecord"];
export type PreRunSourceSpan = Schemas["PreRunSourceSpan"];
export type RunFrozenSourceRecord = Schemas["RunFrozenSourceRecord"];
export type RunFrozenSourceSpan = Schemas["RunFrozenSourceSpan"];

// Recommendation / signoff / decision
export type Recommendation = Schemas["Recommendation"];
export type RecommendationQuality = Schemas["RecommendationQuality"];
export type OptionSystemRecommendation = Schemas["OptionSystemRecommendation"];
export type AbstainSystemRecommendation = Schemas["AbstainSystemRecommendation"];
export type SignoffPayload = Schemas["SignoffPayload"];
export type SignoffRequest = Schemas["SignoffRequest"];

// Validation
export type ValidatorResult = Schemas["ValidatorResult"];
export type ValidatorFinding = Schemas["ValidatorFinding"];
