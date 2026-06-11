import React from 'react';
import {Box, Text} from 'ink';

import type {CommandSnapshot} from '../types.js';

function CommandPickerInner({
	hints,
	selectedIndex,
}: {
	hints: CommandSnapshot[];
	selectedIndex: number;
}): React.JSX.Element | null {
	if (hints.length === 0) {
		return null;
	}

	// Reserve enough room for the longest visible command so the description
	// column lines up cleanly across rows regardless of which one is selected.
	const nameWidth = hints.reduce(
		(max, hint) => Math.max(max, hint.name.length),
		0,
	);

	return (
		<Box flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1} marginBottom={0}>
			<Text dimColor bold> Commands</Text>
			{hints.map((hint, i) => {
				const isSelected = i === selectedIndex;
				const description = hint.description?.trim() ?? '';
				return (
					<Box key={hint.name} flexDirection="row">
						<Box width={nameWidth + 3} flexShrink={0}>
							<Text color={isSelected ? 'cyan' : undefined} bold={isSelected}>
								{isSelected ? '\u276F ' : '  '}
								{hint.name}
							</Text>
						</Box>
						{description ? (
							<Box flexGrow={1} flexShrink={1}>
								<Text
									color={isSelected ? 'cyan' : undefined}
									dimColor={!isSelected}
									wrap="truncate-end"
								>
									{description}
								</Text>
							</Box>
						) : null}
					</Box>
				);
			})}
			<Text dimColor> {'\u2191\u2193'} navigate{'  '}{'\u23CE'} select{'  '}esc dismiss</Text>
		</Box>
	);
}

export const CommandPicker = React.memo(CommandPickerInner);
