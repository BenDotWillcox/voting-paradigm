"use server";

import { eq } from "drizzle-orm";
import { db } from "@/db/db";
import { InsertUser, SelectUser, users } from "../schema/users-schema";

export const createUser = async (data: InsertUser) => {
  try {
    const [newUser] = await db.insert(users).values(data).returning();
    return newUser;
  } catch (error) {
    console.error("Error creating user:", error);
    throw new Error("Failed to create user");
  }
};

export const getUserById = async (id: string) => {
  try {
    const user = await db.query.users.findFirst({
      where: eq(users.id, id),
    });
    if (!user) {
      throw new Error("User not found");
    }
    return user;
  } catch (error) {
    console.error("Error getting user by ID:", error);
    throw new Error("Failed to get user");
  }
};

export const getAllUsers = async (): Promise<SelectUser[]> => {
  return db.query.users.findMany();
};

export const updateUser = async (
  id: string,
  data: Partial<InsertUser>
) => {
  try {
    const [updatedUser] = await db
      .update(users)
      .set(data)
      .where(eq(users.id, id))
      .returning();
    return updatedUser;
  } catch (error) {
    console.error("Error updating user:", error);
    throw new Error("Failed to update user");
  }
};

export const deleteUser = async (id: string) => {
  try {
    await db.delete(users).where(eq(users.id, id));
  } catch (error) {
    console.error("Error deleting user:", error);
    throw new Error("Failed to delete user");
  }
};