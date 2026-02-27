-- Add location and project detail fields to QuotationRequest
ALTER TABLE "quotation_request" ADD COLUMN "region" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "province" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "city" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "barangay" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "street_address" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "landmark" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "project_type" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "delivery_schedule" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "road_type" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "truck_access" TEXT;
ALTER TABLE "quotation_request" ADD COLUMN "estimated_distance" DECIMAL(10,2);
ALTER TABLE "quotation_request" ADD COLUMN "route_preference" TEXT;
