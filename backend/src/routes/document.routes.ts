import { Router, Request, Response } from 'express';
import multer from 'multer';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';
import { auditLog } from '../middleware/audit';
import { config } from '../config';

const router = Router();
router.use(authenticate);

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => {
    fs.mkdirSync(config.uploadDir, { recursive: true });
    cb(null, config.uploadDir);
  },
  filename: (_req, file, cb) => {
    const unique = `${Date.now()}-${crypto.randomBytes(8).toString('hex')}`;
    cb(null, `${unique}${path.extname(file.originalname)}`);
  },
});
const upload = multer({
  storage,
  limits: { fileSize: 20 * 1024 * 1024 }, // 20MB
  fileFilter: (_req, file, cb) => {
    const allowed = ['.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error('Only PDF and image files are accepted'));
  },
});

function hashFile(filePath: string): string {
  const data = fs.readFileSync(filePath);
  return crypto.createHash('sha256').update(data).digest('hex');
}

// POST /api/documents/upload
router.post('/upload', authorize('APPLICANT'), upload.single('file'), async (req: Request, res: Response): Promise<void> => {
  const { applicationId, documentType } = req.body;
  if (!req.file || !applicationId || !documentType) {
    res.status(400).json({ error: 'file, applicationId and documentType are required' });
    return;
  }
  const validTypes = ['AADHAAR', 'PAN', 'SALARY_SLIP', 'BANK_STATEMENT'];
  if (!validTypes.includes(documentType)) {
    res.status(400).json({ error: `documentType must be one of: ${validTypes.join(', ')}` });
    return;
  }
  const app = await prisma.application.findUnique({ where: { id: applicationId } });
  if (!app) { res.status(404).json({ error: 'Application not found' }); return; }
  if (app.applicantId !== req.user!.userId) { res.status(403).json({ error: 'Not your application', code: 'FORBIDDEN' }); return; }

  const sha256 = hashFile(req.file.path);
  const doc = await prisma.document.create({
    data: {
      applicationId,
      type: documentType,
      filePath: req.file.path,
      sha256,
      status: 'PENDING',
    },
  });
  await auditLog(req.user!.userId, 'DOCUMENT_UPLOADED', applicationId, { documentType, documentId: doc.id });
  res.status(201).json({ document: { id: doc.id, type: doc.type, sha256: doc.sha256, status: doc.status } });
});

// GET /api/documents/:id/file — authenticated streaming (owner or staff)
router.get('/:id/file', authorize('APPLICANT', 'OFFICER', 'MANAGER', 'FRAUD_ANALYST', 'AUDITOR'), async (req: Request, res: Response): Promise<void> => {
  const doc = await prisma.document.findUnique({
    where: { id: req.params.id },
    include: { application: { select: { applicantId: true } } },
  });
  if (!doc) { res.status(404).json({ error: 'Document not found' }); return; }
  const isApplicant = req.user!.role === 'APPLICANT';
  if (isApplicant && doc.application.applicantId !== req.user!.userId) {
    res.status(403).json({ error: 'Access denied', code: 'FORBIDDEN' });
    return;
  }
  if (!fs.existsSync(doc.filePath)) {
    res.status(404).json({ error: 'File not found on disk' });
    return;
  }
  res.sendFile(path.resolve(doc.filePath));
});

export default router;
