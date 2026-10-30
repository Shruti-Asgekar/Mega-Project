import { z } from 'zod';

export const SeverityEnum = z.enum(['green', 'amber', 'red']);
export type Severity = z.infer<typeof SeverityEnum>;

export const FindingContractSchema = z.object({
  module: z.number().int(),
  check: z.string(),
  severity: SeverityEnum,
  reason_code: z.string(),
  confidence: z.number().min(0).max(1),
  evidence: z.record(z.any()),
});
export type FindingContract = z.infer<typeof FindingContractSchema>;

// PII masking utilities
export function maskAadhaar(raw: string): string {
  const digits = raw.replace(/\D/g, '');
  if (digits.length !== 12) return 'XXXX-XXXX-XXXX';
  return `XXXX-XXXX-${digits.slice(8)}`;
}

export function maskPan(raw: string): string {
  if (raw.length !== 10) return raw;
  return `${raw.slice(0, 3)}XX${raw.slice(5)}`;
}

export function maskPhone(raw: string): string {
  const digits = raw.replace(/\D/g, '');
  if (digits.length < 4) return '**XXXXXX**';
  return `XXXXXX${digits.slice(-4)}`;
}

// Scan any object and mask known PII fields before logging
export function maskForAudit(obj: Record<string, unknown>): Record<string, unknown> {
  const masked = { ...obj };
  const sensitiveKeys = ['aadhaar', 'aadhaarNumber', 'pan', 'panNumber', 'phone', 'mobile'];
  for (const key of sensitiveKeys) {
    if (masked[key] && typeof masked[key] === 'string') {
      if (key.toLowerCase().includes('aadhaar')) {
        masked[key] = maskAadhaar(masked[key] as string);
      } else if (key.toLowerCase().includes('pan')) {
        masked[key] = maskPan(masked[key] as string);
      } else {
        masked[key] = maskPhone(masked[key] as string);
      }
    }
  }
  return masked;
}
