/** Runtime contracts for the HTTP boundary. The generated types describe the schema;
 *  these schemas prove that the daemon actually answered with it. */

import { z } from "zod";

// The list and the detail disagree on the shape of some fields (a list row has a string
// `source`, a detail has an object), so the contract only insists on identity and state.
export const taskSummarySchema = z
  .object({
    id: z.string().min(1),
    state: z.string().min(1),
  })
  .loose();

export const taskListSchema = z
  .object({ ok: z.boolean().optional(), tasks: z.array(taskSummarySchema) })
  .loose();

export const taskDetailSchema = z
  .object({ ok: z.boolean().optional(), task: taskSummarySchema })
  .loose();

export const healthSchema = z
  .object({
    ok: z.boolean().optional(),
    version: z.union([z.string(), z.number()]).optional(),
    write: z.boolean().optional(),
  })
  .loose();

export const jobStatusSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
]);

export const jobSchema = z.object({ id: z.string().min(1), status: jobStatusSchema }).loose();

export const settingsSchema = z
  .object({ ok: z.boolean().optional(), builder: z.record(z.string(), z.unknown()) })
  .loose();
