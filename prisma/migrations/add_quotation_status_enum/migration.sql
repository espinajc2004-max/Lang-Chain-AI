-- CreateEnum
CREATE TYPE "QuotationStatus" AS ENUM ('DRAFT', 'PENDING', 'VERIFIED', 'APPROVED', 'ACCEPTED', 'REJECTED', 'EXPIRED');

-- AlterTable: Convert existing status column to enum
-- First, update any invalid statuses to DRAFT
UPDATE "Quotation" SET status = 'DRAFT' WHERE status NOT IN ('DRAFT', 'PENDING', 'VERIFIED', 'APPROVED', 'ACCEPTED', 'REJECTED', 'EXPIRED');

-- Change column type to enum
ALTER TABLE "Quotation" ALTER COLUMN "status" DROP DEFAULT;
ALTER TABLE "Quotation" ALTER COLUMN "status" TYPE "QuotationStatus" USING (status::"QuotationStatus");
ALTER TABLE "Quotation" ALTER COLUMN "status" SET DEFAULT 'DRAFT';
