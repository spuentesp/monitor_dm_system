"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Activity,
  GitBranch,
  CheckCircle2,
  Clock,
  AlertCircle,
  Layout,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { storiesApi } from "@/lib/api";
import { STORY_KEYS } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

interface StoryPanelProps {
  storyId: string | null;
}

export function StoryPanel({ storyId }: StoryPanelProps) {
  const { data: story, isLoading, error } = useQuery({
    queryKey: STORY_KEYS.story(storyId || ""),
    queryFn: () => (storyId ? storiesApi.getStory(storyId) : null),
    enabled: !!storyId,
    // Poll every 10s for tension updates — but stop once the story errors
    // (e.g. deleted story) instead of hammering a 404 forever (T-051).
    refetchInterval: (query) => (query.state.error ? false : 10000),
  });

  if (!storyId) {
    return (
      <div className="glass rounded-2xl border border-white/5 p-8 flex flex-col items-center justify-center text-center space-y-3 h-full">
        <BookOpen className="w-10 h-10 text-slate-700" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-slate-400">No active story</p>
          <p className="text-xs text-slate-600 max-w-[200px]">
            Start a new session or select a story to view its progress.
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="glass rounded-2xl border border-white/5 p-4 flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-purple-500/30 border-t-purple-500 rounded-full animate-spin" />
          <p className="text-xs text-slate-500">Reading the threads of fate…</p>
        </div>
      </div>
    );
  }

  if (error || !story) {
    return (
      <div className="glass rounded-2xl border border-white/5 p-4 flex flex-col items-center justify-center text-center space-y-2 h-full">
        <AlertCircle className="w-8 h-8 text-red-500/50" />
        <p className="text-xs text-slate-500">Failed to load story details</p>
      </div>
    );
  }

  // Calculate tension percentage (backend provides 0.0-1.0)
  const tensionPercent = Math.min(Math.max(story.tension_score * 100, 0), 100);

  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-6 h-full flex flex-col overflow-y-auto custom-scrollbar">
      {/* Header & Arc Status */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-200">
            <Layout className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-semibold">Story Arc</h2>
          </div>
          <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[10px] font-bold text-cyan-400 uppercase tracking-wider">
            {story.arc_label || "Development"}
          </span>
        </div>

        {/* Tension Meter */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider font-bold">
            <div className="flex items-center gap-1.5 text-slate-400">
              <Activity className="w-3 h-3 text-purple-400" />
              <span>Narrative Tension</span>
            </div>
            <span className={cn(
              "font-mono",
              story.tension_score > 0.7 ? "text-red-400" : 
              story.tension_score > 0.4 ? "text-amber-400" : "text-emerald-400"
            )}>
              {(story.tension_score * 10).toFixed(1)} / 10.0
            </span>
          </div>
          <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${tensionPercent}%` }}
              className={cn(
                "h-full transition-all duration-1000",
                story.tension_score > 0.7 ? "bg-gradient-to-r from-orange-500 to-red-500" : 
                story.tension_score > 0.4 ? "bg-gradient-to-r from-amber-500 to-orange-500" : 
                "bg-gradient-to-r from-emerald-500 to-teal-500"
              )}
            />
          </div>
        </div>
      </div>

      {/* Plot Threads */}
      <div className="space-y-4 flex-1">
        {/* Active Threads */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-slate-500">
            <GitBranch className="w-3 h-3" />
            <span>Active Plot Threads</span>
          </div>
          <div className="space-y-1.5">
            {story.active_threads.length === 0 ? (
              <p className="text-[10px] text-slate-600 italic px-2">No active threads</p>
            ) : (
              story.active_threads.map((thread, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -5 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  className="group flex items-start gap-2.5 p-2 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-all"
                >
                  <div className="mt-1 w-1.5 h-1.5 rounded-full bg-cyan-400/50 group-hover:bg-cyan-400 transition-colors flex-shrink-0" />
                  <span className="text-xs text-slate-300 leading-tight">{thread}</span>
                </motion.div>
              ))
            )}
          </div>
        </div>

        {/* Completed Threads */}
        {story.completed_threads.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-white/5">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-slate-500">
              <CheckCircle2 className="w-3 h-3 text-emerald-500/50" />
              <span>Resolved Threads</span>
            </div>
            <div className="space-y-1.5 opacity-60">
              {story.completed_threads.slice(0, 3).map((thread, idx) => (
                <div key={idx} className="flex items-start gap-2.5 px-2">
                  <CheckCircle2 className="mt-0.5 w-3 h-3 text-emerald-500/40 flex-shrink-0" />
                  <span className="text-[10px] text-slate-400 line-through decoration-slate-600">{thread}</span>
                </div>
              ))}
              {story.completed_threads.length > 3 && (
                <p className="text-[9px] text-slate-600 px-6">
                  + {story.completed_threads.length - 3} more resolved
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="pt-4 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-600">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          <span>{story.scenes_completed} scenes completed</span>
        </div>
        {story.next_scene_type && (
          <div className="flex items-center gap-1.5 italic text-slate-500">
            <span>Next: {story.next_scene_type}</span>
          </div>
        )}
      </div>
    </div>
  );
}
