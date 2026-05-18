import { describe, it, expect } from "vitest";
import { isErrorBodyWithDetail } from "@/lib/api";

describe("isErrorBodyWithDetail", () => {
  it("retourne true si body.detail === expected", () => {
    expect(isErrorBodyWithDetail({ detail: "rerank_not_configured" }, "rerank_not_configured")).toBe(true);
  });

  it("retourne false si body.detail !== expected", () => {
    expect(isErrorBodyWithDetail({ detail: "workspace_not_found" }, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body n'a pas de champ detail", () => {
    expect(isErrorBodyWithDetail({ message: "boom" }, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est null", () => {
    expect(isErrorBodyWithDetail(null, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est une string", () => {
    expect(isErrorBodyWithDetail("oops", "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body.detail n'est pas une string", () => {
    expect(isErrorBodyWithDetail({ detail: 42 }, "rerank_not_configured")).toBe(false);
  });
});
