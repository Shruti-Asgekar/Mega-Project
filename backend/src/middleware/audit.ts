import { Request, Response, NextFunction } from 'express';
import { prisma } from '../db';
import { maskForAudit } from '../utils/contracts';

export async function auditLog(
  userId: string,
  action: string,
  applicationId?: string,
  meta?: Record<string, unknown>
): Promise<void> {
  try {
    await prisma.auditLog.create({
      data: {
        userId,
        action,
        applicationId: applicationId || null,
        metadataJson: meta ? maskForAudit(meta) : undefined,
      },
    });
  } catch {
    // Audit logging must never crash the primary request
    console.error(`[AUDIT] Failed to write audit log for action ${action}`);
  }
}

// Middleware that auto-logs every mutating request
export function auditMiddleware(action: string) {
  return async (req: Request, _res: Response, next: NextFunction): Promise<void> => {
    if (req.user) {
      const appId = req.params.id || req.body?.applicationId;
      await auditLog(req.user.userId, action, appId, {
        ip: req.ip,
        method: req.method,
        path: req.path,
      });
    }
    next();
  };
}
