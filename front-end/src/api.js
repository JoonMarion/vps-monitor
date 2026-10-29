let csrfToken = "";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest(path, { body, ...options } = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Não foi possível conectar ao servidor. Tente novamente.", 0);
  }
  const data = await response.json().catch(() => null);
  if (typeof data?.csrf_token === "string") csrfToken = data.csrf_token;
  if (!response.ok) {
    throw new ApiError(data?.error || "Não foi possível concluir a operação.", response.status);
  }
  if (data === null) throw new ApiError("O servidor enviou uma resposta inválida.", response.status);
  return data;
}
