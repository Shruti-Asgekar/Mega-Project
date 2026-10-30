import { Router, Request, Response } from 'express';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';

const router = Router();
router.use(authenticate);

// GET /api/audit/logs — filterable audit trail (AUDITOR, ADMIN only)
router.get('/logs', authorize('AUDITOR', 'ADMIN'), async (req: Request, res: Response): Promise<void> => {
  const page = Math.max(1, parseInt(req.query.page as string || '1', 10));
  const limit = Math.min(100, parseInt(req.query.limit as string || '50', 10));
  const action = req.query.action as string | undefined;
  const userId = req.query.userId as string | undefined;
  const applicationId = req.query.applicationId as string | undefined;

  const where: Record<string, unknown> = {};
  if (action) where.action = action;
  if (userId) where.userId = userId;
  if (applicationId) where.applicationId = applicationId;

  const [logs, total] = await Promise.all([
    prisma.auditLog.findMany({
      where,
      include: { user: { select: { id: true, name: true, role: true } } },
      orderBy: { createdAt: 'desc' },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.auditLog.count({ where }),
  ]);

  res.json({ logs, total, page, limit, totalPages: Math.ceil(total / limit) });
});

export default router;
