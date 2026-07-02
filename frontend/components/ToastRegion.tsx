"use client";

import { Toast } from "@base-ui/react/toast";
import { cn } from "@/lib/utils";

export function ToastRegion() {
  const { toasts } = Toast.useToastManager();

  return (
    <Toast.Viewport className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 w-80">
      {toasts.map((toast) => (
        <Toast.Root
          key={toast.id}
          toast={toast}
          className={cn(
            "flex flex-col gap-1 rounded-[3px] border border-edge bg-surface px-4 py-3 shadow-sm",
            "data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0",
            "data-[ending-style]:translate-y-2 data-[ending-style]:opacity-0",
            "transition-all duration-150",
            toast.type === "error" && "border-l-2 border-l-red-500",
          )}
        >
          <Toast.Content className="flex items-start justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              {toast.title && (
                <Toast.Title className="font-sans font-medium text-[13px] text-fg">
                  {toast.title}
                </Toast.Title>
              )}
              {toast.description && (
                <Toast.Description className="font-sans text-[12px] text-subtle leading-relaxed">
                  {toast.description}
                </Toast.Description>
              )}
            </div>
            <Toast.Close
              aria-label="Dismiss"
              className="text-muted-fg hover:text-fg font-mono text-[14px] leading-none flex-none transition-colors"
            >
              ×
            </Toast.Close>
          </Toast.Content>
        </Toast.Root>
      ))}
    </Toast.Viewport>
  );
}
