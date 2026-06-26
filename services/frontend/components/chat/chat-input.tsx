export default function ChatInput() {
  return (
    <div className="flex gap-2">
      <input type="text" placeholder="Type your message..." className="flex-1 border rounded px-3 py-2" />

      <button className="border rounded px-4 py-2">Send</button>
    </div>
  );
}
