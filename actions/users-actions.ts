"use server";

import {
  createUser,
  deleteUser,
  getAllUsers,
  getUserById,
  updateUser,
} from "@/db/queries/users-queries";
import { InsertUser, SelectUser } from "@/db/schema/users-schema";
import { ActionResult } from "@/types/actions/action-types";
import { revalidatePath } from "next/cache";

export async function createUserAction(
  data: InsertUser
): Promise<ActionResult<SelectUser>> {
  try {
    const newUser = await createUser(data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "User created successfully",
      data: newUser,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to create user" };
  }
}

export async function getUserByIdAction(
  id: string
): Promise<ActionResult<SelectUser | null>> {
  try {
    const user = await getUserById(id);
    return {
      isSuccess: true,
      message: "User retrieved successfully",
      data: user,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get user" };
  }
}

export async function getAllUsersAction(): Promise<
  ActionResult<SelectUser[]>
> {
  try {
    const users = await getAllUsers();
    return {
      isSuccess: true,
      message: "Users retrieved successfully",
      data: users,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to get users" };
  }
}

export async function updateUserAction(
  id: string,
  data: Partial<InsertUser>
): Promise<ActionResult<SelectUser>> {
  try {
    const updatedUser = await updateUser(id, data);
    revalidatePath("/");
    return {
      isSuccess: true,
      message: "User updated successfully",
      data: updatedUser,
    };
  } catch (error) {
    return { isSuccess: false, message: "Failed to update user" };
  }
}

export async function deleteUserAction(
  id: string
): Promise<ActionResult<void>> {
  try {
    await deleteUser(id);
    revalidatePath("/");
    return { isSuccess: true, message: "User deleted successfully" };
  } catch (error) {
    return { isSuccess: false, message: "Failed to delete user" };
  }
}

