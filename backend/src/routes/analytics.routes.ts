import { Router, Request, Response } from 'express';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';

const router = Router();
router.use(authenticate);

// GET /api/analytics/metrics
router.get('/metrics', authorize('MANAGER', 'ADMIN', 'AUDITOR'), async (_req: Request, res: Response): Promise<void> => {
  const [totalApps, statusBreakdown, severityBreakdown, routingBreakdown] = await Promise.all([
    prisma.application.count(),
    prisma.application.groupBy({ by: ['status'], _count: true }),
    prisma.finding.groupBy({ by: ['severity'], _count: true }),
    prisma.application.groupBy({ by: ['routing'], _count: true, where: { routing: { not: null } } }),
  ]);

  res.json({
    totalApplications: totalApps,
    byStatus: statusBreakdown.map(s => ({ status: s.status, count: s._count })),
    bySeverity: severityBreakdown.map(s => ({ severity: s.severity, count: s._count })),
    byRouting: routingBreakdown.map(r => ({ routing: r.routing, count: r._count })),
  });
});

export default router;
