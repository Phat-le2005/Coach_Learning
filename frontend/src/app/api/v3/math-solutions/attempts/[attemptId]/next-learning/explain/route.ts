import { proxyNextLearning } from "@/lib/api/next-learning-proxy";
export const POST = (request: Parameters<typeof proxyNextLearning>[0], context: Parameters<typeof proxyNextLearning>[1]) => proxyNextLearning(request, context, true);
