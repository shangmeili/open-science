import { render } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter, useRoutes } from "react-router-dom";
import { routes } from "@/app/router";

/** Render the whole app at a given route, using an in-memory router. */
export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

/** Render with React Router's declarative memory history. Prefer this helper
 * for tests that click between routes: unlike the data router it does not
 * construct a Node Request with jsdom's AbortSignal. */
export function renderNavigableAt(path: string) {
  function TestRoutes() {
    return useRoutes(routes);
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TestRoutes />
    </MemoryRouter>,
  );
}
