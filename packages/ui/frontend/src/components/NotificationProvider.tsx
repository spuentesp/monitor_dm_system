"use client";

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type NotificationType = "success" | "error" | "info";

interface Notification {
  id: string;
  type: NotificationType;
  message: string;
}

interface NotificationContextType {
  notify: (type: NotificationType, message: string) => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const timeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Clear all pending timeouts on unmount.
  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach((tid) => clearTimeout(tid));
    };
  }, []);

  const notify = useCallback((type: NotificationType, message: string) => {
    const id = crypto.randomUUID();
    setNotifications((prev) => [...prev, { id, type, message }]);
    const tid = setTimeout(() => {
      timeoutsRef.current.delete(id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, 5000);
    timeoutsRef.current.set(id, tid);
  }, []);

  const remove = (id: string) => {
    const tid = timeoutsRef.current.get(id);
    if (tid !== undefined) {
      clearTimeout(tid);
      timeoutsRef.current.delete(id);
    }
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-md w-full pointer-events-none">
        <AnimatePresence>
          {notifications.map((n) => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, x: 20, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 20, scale: 0.95 }}
              className={cn(
                "pointer-events-auto flex items-start gap-3 p-4 rounded-xl border shadow-2xl glass",
                n.type === "success" && "border-emerald-500/20 bg-emerald-500/5 text-emerald-300",
                n.type === "error" && "border-red-500/20 bg-red-500/5 text-red-300",
                n.type === "info" && "border-cyan-500/20 bg-cyan-500/5 text-cyan-300"
              )}
            >
              <div className="mt-0.5">
                {n.type === "success" && <CheckCircle2 className="w-4 h-4" />}
                {n.type === "error" && <AlertCircle className="w-4 h-4" />}
                {n.type === "info" && <Info className="w-4 h-4" />}
              </div>
              <p className="text-sm font-medium flex-1">{n.message}</p>
              <button 
                onClick={() => remove(n.id)}
                className="p-1 -mr-1 -mt-1 rounded-lg hover:bg-white/10 transition-colors"
              >
                <X className="w-3.5 h-3.5 opacity-50" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </NotificationContext.Provider>
  );
}

export function useNotify() {
  const context = useContext(NotificationContext);
  if (!context) throw new Error("useNotify must be used within NotificationProvider");
  return context;
}
