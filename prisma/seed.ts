// Seed script using same Prisma 7 Driver Adapter pattern as lib/prisma.ts
import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import { Pool } from "pg";
import bcrypt from "bcryptjs";

function createPrismaClient() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL environment variable is not set");
  }
  const pool = new Pool({ connectionString });
  const adapter = new PrismaPg(pool);
  return new PrismaClient({ adapter });
}

async function main() {
  console.log("🌱 Starting seed...");

  const prisma = createPrismaClient();

  try {
    // Super admin credentials
    const SUPER_ADMIN_USERNAME = "super_admin";
    const SUPER_ADMIN_PASSWORD = "superadmin123";
    const SUPER_ADMIN_NAME = "Super Administrator";

    // Hash password with bcrypt (matches auth.ts config)
    const hashedPassword = await bcrypt.hash(SUPER_ADMIN_PASSWORD, 10);

    // Check if super_admin already exists
    const existingUser = await prisma.user.findUnique({
      where: { username: SUPER_ADMIN_USERNAME },
    });

    if (existingUser) {
      console.log("⚠️  Super admin already exists, skipping...");
      return;
    }

    // Create user with account and employee profile in a transaction
    const superAdmin = await prisma.$transaction(async (tx) => {
      // Create the user
      const user = await tx.user.create({
        data: {
          username: SUPER_ADMIN_USERNAME,
          name: SUPER_ADMIN_NAME,
          email: "superadmin@auggregates.local",
          emailVerified: true,
        },
      });

      // Create the credential account (for username/password login)
      await tx.account.create({
        data: {
          userId: user.id,
          providerId: "credential",
          accountId: user.id,
          password: hashedPassword,
        },
      });

      // Create the employee profile with SUPER_ADMIN role
      await tx.employeeProfile.create({
        data: {
          userId: user.id,
          fullName: SUPER_ADMIN_NAME,
          role: "SUPER_ADMIN",
          isActive: true,
        },
      });

      return user;
    });

    console.log("✅ Super admin created successfully!");
    console.log(`   Username: ${SUPER_ADMIN_USERNAME}`);
    console.log(`   Password: ${SUPER_ADMIN_PASSWORD}`);
    console.log(`   User ID: ${superAdmin.id}`);

    // Seed locations
    console.log("\n🌱 Seeding locations...");
    await seedLocations(prisma);
  } finally {
    await prisma.$disconnect();
  }
}

async function seedLocations(prisma: PrismaClient) {
  // Create default main location
  const mainLocation = await prisma.location.upsert({
    where: { slug: "main-office" },
    update: {},
    create: {
      name: "Main Office",
      slug: "main-office",
      code: "MAIN",
      city: "Manila",
      region: "NCR",
      address: "Main Office Address",
      isActive: true,
    },
  });

  console.log(
    `✅ Created location: ${mainLocation.name} (${mainLocation.code})`,
  );

  // Assign all existing dispatchers to main location
  const dispatcherUpdate = await prisma.employeeProfile.updateMany({
    where: {
      role: "DISPATCHER",
      locationId: null,
    },
    data: {
      locationId: mainLocation.id,
    },
  });

  console.log(
    `✅ Assigned ${dispatcherUpdate.count} dispatchers to ${mainLocation.name}`,
  );

  // Assign all existing trucks to main location
  const truckUpdate = await prisma.truckDetails.updateMany({
    where: {
      locationId: null,
    },
    data: {
      locationId: mainLocation.id,
    },
  });

  console.log(
    `✅ Assigned ${truckUpdate.count} trucks to ${mainLocation.name}`,
  );

  // Optionally create additional locations (commented out by default)
  /*
    const cebuLocation = await prisma.location.upsert({
        where: { slug: "cebu-branch" },
        update: {},
        create: {
            name: "Cebu Branch",
            slug: "cebu-branch",
            code: "CEB",
            city: "Cebu City",
            region: "Central Visayas",
            isActive: true,
        },
    });
    console.log(`✅ Created location: ${cebuLocation.name} (${cebuLocation.code})`);
    */
}

main().catch((e) => {
  console.error("❌ Seed failed:", e);
  process.exit(1);
});
