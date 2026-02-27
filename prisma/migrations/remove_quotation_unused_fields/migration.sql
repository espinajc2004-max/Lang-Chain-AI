-- AlterTable: Remove unused fields from Quotation table
ALTER TABLE "Quotation" DROP COLUMN IF EXISTS "default_distance_km";
ALTER TABLE "Quotation" DROP COLUMN IF EXISTS "fuel_rate";

-- AlterTable: Remove source_quarry from QuotationItem
ALTER TABLE "QuotationItem" DROP COLUMN IF EXISTS "source_quarry";

-- Update existing NULL values before making fields required
UPDATE "QuotationItem" SET "plate_no" = 'N/A' WHERE "plate_no" IS NULL;
UPDATE "QuotationItem" SET "dr_no" = 'N/A' WHERE "dr_no" IS NULL;

-- Make plate_no and dr_no required
ALTER TABLE "QuotationItem" ALTER COLUMN "plate_no" SET NOT NULL;
ALTER TABLE "QuotationItem" ALTER COLUMN "dr_no" SET NOT NULL;
