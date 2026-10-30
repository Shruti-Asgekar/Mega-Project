import { Router, Request, Response } from 'express';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';
import { auditLog } from '../middleware/audit';

const router = Router();
router.use(authenticate);

// POST /api/applications — create new draft application (APPLICANT only)
router.post('/', authorize('APPLICANT'), async (req: Request, res: Response): Promise<void> => {
  const { consentText } = req.body;
  if (!consentText) {
    res.status(400).json({ error: 'Explicit consent is required before creating an application', code: 'CONSENT_REQUIRED' });
    return;
  }
  const application = await prisma.application.create({
    data: {
      applicantId: req.user!.userId,
      status: 'DRAFT',
      consents: {
        create: {
          userId: req.user!.userId,
          text: consentText,
        },
      },
    },
    include: { consents: true },
  });
  await auditLog(req.user!.userId, 'APPLICATION_CREATED', application.id);
  res.status(201).json({ application });
});

// GET /api/applications/my — applicant sees their own application (masked)
router.get('/my', authorize('APPLICANT'), async (req: Request, res: Response): Promise<void> => {
  const applications = await prisma.application.findMany({
    where: { applicantId: req.user!.userId },
    select: {
      id: true, status: true, routing: true, createdAt: true, updatedAt: true,
      documents: { select: { id: true, type: true, status: true, createdAt: true } },
      jobs: { select: { id: true, step: true, status: true, error: true, updatedAt: false } },
    },
    orderBy: { createdAt: 'desc' },
  });
  res.json({ applications });
});

// POST /api/applications/:id/submit — lock and enqueue processing
router.post('/:id/submit', authorize('APPLICANT'), async (req: Request, res: Response): Promise<void> => {
  const { id } = req.params;
  const app = await prisma.application.findUnique({
    where: { id },
    include: { documents: true, consents: true },
  });
  if (!app) { res.status(404).json({ error: 'Application not found' }); return; }
  if (app.applicantId !== req.user!.userId) { res.status(403).json({ error: 'Not your application', code: 'FORBIDDEN' }); return; }
  if (app.status !== 'DRAFT') { res.status(400).json({ error: 'Application already submitted', code: 'ALREADY_SUBMITTED' }); return; }
  if (app.consents.length === 0) { res.status(400).json({ error: 'Consent record missing', code: 'CONSENT_REQUIRED' }); return; }
  if (app.documents.length === 0) { res.status(400).json({ error: 'Please upload at least one document before submitting', code: 'NO_DOCUMENTS' }); return; }

  await prisma.application.update({ where: { id }, data: { status: 'SUBMITTED' } });
  await prisma.processingJob.create({
    data: { applicationId: id, status: 'QUEUED', step: 'OCR' },
  });
  await auditLog(req.user!.userId, 'APPLICATION_SUBMITTED', id);
  res.json({ message: 'Application submitted. Processing has started.', applicationId: id });
});

// GET /api/applications/:id/job — poll processing progress
router.get('/:id/job', authorize('APPLICANT', 'OFFICER', 'MANAGER'), async (req: Request, res: Response): Promise<void> => {
  const { id } = req.params;
  const job = await prisma.processingJob.findFirst({
    where: { applicationId: id },
    orderBy: { createdAt: 'desc' },
  });
  res.json({ job });
});

// GET /api/officer/queue — sortable review queue for officers/managers
router.get('/queue', authorize('OFFICER', 'MANAGER', 'FRAUD_ANALYST', 'AUDITOR'), async (req: Request, res: Response): Promise<void> => {
  const page = Math.max(1, parseInt(req.query.page as string || '1', 10));
  const limit = Math.min(50, parseInt(req.query.limit as string || '20', 10));

  const [applications, total] = await Promise.all([
    prisma.application.findMany({
      where: { status: { in: ['SUBMITTED', 'PROCESSING', 'NEEDS_REVIEW', 'RECOMMENDED'] } },
      include: {
        applicant: { select: { id: true, name: true, email: true } },
        assignedOfficer: { select: { id: true, name: true } },
        documents: { select: { id: true, type: true, status: true } },
      },
      orderBy: { createdAt: 'desc' },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.application.count({
      where: { status: { in: ['SUBMITTED', 'PROCESSING', 'NEEDS_REVIEW', 'RECOMMENDED'] } },
    }),
  ]);

  res.json({ applications, total, page, limit, totalPages: Math.ceil(total / limit) });
});

// GET /api/applications/:id — full case view for staff
router.get('/:id', authorize('OFFICER', 'MANAGER', 'FRAUD_ANALYST', 'AUDITOR'), async (req: Request, res: Response): Promise<void> => {
  const { id } = req.params;
  const app = await prisma.application.findUnique({
    where: { id },
    include: {
      applicant: { select: { id: true, name: true, email: true, role: true } },
      assignedOfficer: { select: { id: true, name: true } },
      documents: { include: { extractedFields: true, ledgerEntry: true } },
      findings: { orderBy: [{ severity: 'desc' }, { createdAt: 'desc' }] },
      decisions: { include: { user: { select: { id: true, name: true, role: true } } }, orderBy: { createdAt: 'asc' } },
      jobs: { orderBy: { createdAt: 'desc' }, take: 1 },
    },
  });
  if (!app) { res.status(404).json({ error: 'Application not found' }); return; }
  res.json({ application: app });
});

export default router;
