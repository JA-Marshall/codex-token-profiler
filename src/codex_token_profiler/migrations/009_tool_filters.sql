ALTER TABLE tool_calls ADD COLUMN model TEXT;
ALTER TABLE tool_calls ADD COLUMN project TEXT;
CREATE INDEX tool_filters ON tool_calls(project,model,timestamp);
