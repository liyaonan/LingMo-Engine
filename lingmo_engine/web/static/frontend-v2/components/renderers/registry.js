// renderers/registry.js
import { renderHeader } from './header.js';
import { renderPoolGroup } from './pool-group.js';
import { renderStatGrid } from './stat-grid.js';
import { renderKeyedList } from './keyed-list.js';
import {
  renderText, renderList, renderTagList,
  renderMemoryList, renderRelationshipList, renderLootList
} from './simple-renderers.js';

const RENDERERS = {
  header: renderHeader,
  pool_group: renderPoolGroup,
  stat_grid: renderStatGrid,
  keyed_list: renderKeyedList,
  text: renderText,
  list: renderList,
  tag_list: renderTagList,
  memory_list: renderMemoryList,
  relationship_list: renderRelationshipList,
  loot_list: renderLootList,
};

export { RENDERERS };
