import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useLocalStorageState } from "./useLocalStorageState";

const KEY = "elenchos.test.prefs";

afterEach(() => {
  localStorage.removeItem(KEY);
});

describe("useLocalStorageState", () => {
  it("reads initial value when storage is empty", () => {
    const { result } = renderHook(() =>
      useLocalStorageState(KEY, { mode: "rubric" }),
    );
    expect(result.current[0]).toEqual({ mode: "rubric" });
  });

  it("restores value from localStorage", () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({ mode: "pairwise", judgeProvider: "ollama" }),
    );

    const { result } = renderHook(() =>
      useLocalStorageState(KEY, { mode: "rubric", judgeProvider: "" }),
    );

    expect(result.current[0]).toEqual({
      mode: "pairwise",
      judgeProvider: "ollama",
    });
  });

  it("persists updates to localStorage", () => {
    const { result } = renderHook(() =>
      useLocalStorageState(KEY, { judgeModel: "" }),
    );

    act(() => {
      result.current[1]({ judgeModel: "llama3.1:8b" });
    });

    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual({
      judgeModel: "llama3.1:8b",
    });
  });
});
