import { Router, Request, Response } from 'express';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';
import { auditLog } from '../middleware/audit';

const router = Router();
router.use(authenticate);

// POST /api/decisions/recommend — Officer/Manager submits recommendation
router.post('/recommend', authorize('OFFICER', 'MANAGER'), async (req: Request, res: Response): Promise<void> => {
  const { applicationId, outcome, reason } = req.body;
  const validOutcomes = ['APPROVED', 'REJECTED', 'MORE_DOCS_REQUESTED'];
  if (!applicationId || !outcome || !reason) {
    res.status(400).json({ error: 'applicationId, outcome and reason are required' });
    return;
  }
  if (!validOutcomes.includes(outcome)) {
    res.status(400).json({ error: `outcome must be one of: ${validOutcomes.join(', ')}` });
    return;
  }
  const app = await prisma.application.findUnique({ where: { id: applicationId } });
  if (!app) { res.status(404).json({ error: 'Application not found' }); return; }

  const decision = await prisma.decision.create({
    data: { applicationId, userId: req.user!.userId, kind: 'RECOMMENDATION', outcome, reason },
  });
  await prisma.application.update({ where: { id: applicationId }, data: { status: 'RECOMMENDED' } });
  await auditLog(req.user!.userId, 'RECOMMENDATION_SUBMITTED', applicationId, { outcome, decisionId: decision.id });
  res.status(201).json({ decision });
});

// POST /api/decisions/final — Manager gives final approval (Maker-Checker enforced)
router.post('/final', authorize('MANAGER'), async (req: Request, res: Response): Promise<void> => {
  const { applicationId, outcome, reason } = req.body;
  const validOutcomes = ['APPROVED', 'REJECTED', 'MORE_DOCS_REQUESTED'];
  if (!applicationId || !outcome || !reason) {
    res.status(400).json({ error: 'applicationId, outcome and reason are required' });
    return;
  }
  if (!validOutcomes.includes(outcome)) {
    res.status(400).json({ error: `outcome must be one of: ${validOutcomes.join(', ')}` });
    return;
  }

  // MAKER-CHECKER: block if this manager also submitted the RECOMMENDATION
  const priorRecommendation = await prisma.decision.findFirst({
    where: { applicationId, kind: 'RECOMMENDATION', userId: req.user!.userId },
  });
  if (priorRecommendation) {
    res.status(403).json({
      error: 'The person who recommended this decision cannot give the final approval. This is a maker-checker control.',
      code: 'MAKER_CHECKER_VIOLATION',
    });
    return;
  }

  const decision = await prisma.decision.create({
    data: { applicationId, userId: req.user!.userId, kind: 'FINAL', outcome, reason },
  });

  const statusMap: Record<string, string> = { APPROVED: 'APPROVED', REJECTED: 'REJECTED', MORE_DOCS_REQUESTED: 'MORE_DOCS_REQUESTED' };
  await prisma.application.update({ where: { id: applicationId }, data: { status: statusMap[outcome] as any } });
  await auditLog(req.user!.userId, 'FINAL_DECISION', applicationId, { outcome, decisionId: decision.id });
  res.status(201).json({ decision });
});

export default router;
