import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SavedPermissionsCard } from "./SavedPermissionsCard";

describe("SavedPermissionsCard", () => {
  it("shows exact project rules and revokes one through the runtime", async () => {
    const listSavedPermissions = vi.fn()
      .mockResolvedValueOnce([
        {
          id: "psv_1",
          projectId: "project_1",
          action: "bash",
          resource: "python3 -B analysis.py",
        },
      ])
      .mockResolvedValueOnce([]);
    const removeSavedPermission = vi.fn().mockResolvedValue(undefined);

    render(
      <SavedPermissionsCard
        connected
        workspace="/research/project one"
        client={{ listSavedPermissions, removeSavedPermission }}
      />,
    );

    expect(await screen.findByText("python3 -B analysis.py")).toBeInTheDocument();
    expect(screen.getByText(/current project and exact target/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /revoke/i }));
    expect(listSavedPermissions).toHaveBeenCalledWith("/research/project one");
    expect(removeSavedPermission).toHaveBeenCalledWith("psv_1", "/research/project one");
    expect(await screen.findByText(/no saved permissions/i)).toBeInTheDocument();
  });

  it("does not invent saved rules while the runtime is disconnected", () => {
    render(<SavedPermissionsCard connected={false} workspace={null} client={null} />);
    expect(screen.getByText(/connect the local service/i)).toBeInTheDocument();
  });
});
