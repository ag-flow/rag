import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { eventsProducerApi } from "@/lib/events-producer";
import type {
  EventsProducerConfig,
  EventsProducerSpec,
  TestConnectionResult,
} from "@/lib/events-producer.types";

const QUERY_KEY = ["events-producer"] as const;

export function useEventsProducerConfig() {
  return useQuery<EventsProducerConfig>({
    queryKey: QUERY_KEY,
    queryFn: () => eventsProducerApi.get(),
  });
}

export function useSaveEventsProducer() {
  const qc = useQueryClient();
  return useMutation<EventsProducerConfig, Error, EventsProducerSpec>({
    mutationFn: (payload) => eventsProducerApi.save(payload),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data);
      void qc.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useTestEventsProducerConnection() {
  return useMutation<TestConnectionResult, Error, void>({
    mutationFn: () => eventsProducerApi.testConnection(),
  });
}
