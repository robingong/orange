import orange
import orngFSS
import statc
import orngCI
from Numeric import *
from LinearAlgebra import *

###########################################################################################
##### FUNCTIONS FOR CALCULATING ATTRIBUTE ORDER USING Oblivious decision graphs
###########################################################################################
def replaceAttributes(index1, index2, merged, data):
	attrs = list(data.domain)
	attrs.remove(data.domain[index1])
	attrs.remove(data.domain[index2])
	domain = orange.Domain(attrs+ [merged])
	return data.select(domain)


def getFunctionalList(data):
	bestQual = -10000000
	bestAttr = -1
	testAttrs = []

	dataShort = orange.Preprocessor_dropMissing(data)
	# remove continuous attributes from data
	disc = []
	for i in range(len(dataShort.domain.attributes)):
		# keep only discrete attributes that have more than one value
		if dataShort.domain.attributes[i].varType == orange.VarTypes.Discrete and len(dataShort.domain.attributes[i].values) > 1: disc.append(dataShort.domain.attributes[i].name)
	if disc == []: return []
	discData = dataShort.select(disc + [dataShort.domain.classVar.name])

	remover = orngCI.AttributeRedundanciesRemover(noMinimization = 1)
	newData = remover(discData, weight = 0)

	for attr in newData.domain.attributes: testAttrs.append(attr.name)

	# compute the best attribute combination
	for i in range(len(newData.domain.attributes)):
		vals, qual = orngCI.FeatureByMinComplexity(newData, [newData.domain.attributes[i], newData.domain.classVar])
		if qual > bestQual:
			bestQual = qual
			bestAttr = newData.domain.attributes[i].name
			mergedVals = vals
			mergedVals.name = newData.domain.classVar.name

	if bestAttr == -1: return []
	outList = [bestAttr]
	newData = replaceAttributes(bestAttr, newData.domain.classVar, mergedVals, newData)
	testAttrs.remove(bestAttr)
	
	while (testAttrs != []):
		bestQual = -10000000
		for attrName in testAttrs:
			vals, qual = orngCI.FeatureByMinComplexity(newData, [mergedVals, attrName])
			if qual > bestQual:
				bestqual = qual
				bestAttr = attrName

		vals, qual = orngCI.FeatureByMinComplexity(newData, [mergedVals, bestAttr])
		mergedVals = vals
		mergedVals.name = newData.domain.classVar.name
		newData = replaceAttributes(bestAttr, newData.domain.classVar, mergedVals, newData)
		outList.append(bestAttr)
		testAttrs.remove(bestAttr)

	# new attributes have "'" at the end of their names. we have to remove that in ored to identify them in the old domain
	for index in range(len(outList)):
		if outList[index][-1] == "'": outList[index] = outList[index][:-1]
	return outList


###########################################################################################
##### FUNCTIONS FOR CALCULATING ATTRIBUTE ORDER USING Fisher discriminant analysis
###########################################################################################

# fisher discriminant implemented to be used as orange.MeasureAttribute
class MeasureFisherDiscriminant:
	def __init__(self):
		self.dataset = None
		self.attrInfo = {}
		self.stats = []

	def __call__(self, attr, data):
		return self.MeasureAttribute_info(attr, data)

	def MeasureAttribute_info(self, attr, data):
		# if basic statistics is not computed for this dataset -> compute it
		if not (self.stats and self.dataset == data):
			self.stats = {}
			self.dataset = data

			arr = [0] * len(data.domain.attributes)
			for val in data.domain.classVar.values:
				data2 = data.select({data.domain.classVar: val})
				bas = orange.DomainBasicAttrStat(data2)
				self.stats[val] = bas

			for i in range(len(self.stats.keys())):
				for j in range(i+1, len(self.stats.keys())):
					statI = self.stats[self.stats.keys()[i]]
					statJ = self.stats[self.stats.keys()[j]]
					for attribute in range(len(data.domain.attributes)):
						sumDev = statI[attribute].dev + statJ[attribute].dev
						val = abs(statI[attribute].avg - statJ[attribute].avg)/(statI[attribute].dev + statJ[attribute].dev)
						arr[attribute] += val

			# normalize values in arr so that the largest value will be 1 and others will be proportionally smaller
			largest = max(arr)
			arr = [val/largest for val in arr]

			for i in range(len(data.domain.attributes)):
				self.attrInfo[data.domain.attributes[i].name] = arr[i]

		return self.attrInfo[data.domain[attr].name]


# used by kNN optimization to evaluate attributes
def evaluateAttributes(data, contMeasure, discMeasure):
	attrs = []
	for attr in data.domain.attributes:
		if   discMeasure == None and attr.varType == orange.VarTypes.Discrete:   attrs.append((0.1, attr.name))
		elif contMeasure == None and attr.varType == orange.VarTypes.Continuous: attrs.append((0.1, attr.name))
		elif attr.varType == orange.VarTypes.Continuous: attrs.append((contMeasure(attr.name, data), attr.name))
		else: 											 attrs.append((discMeasure(attr.name, data), attr.name))
	return attrs
		

	
# ##############################################################################################
# ##############################################################################################



##############################################
# SELECT ATTRIBUTES ##########################
##############################################
def selectAttributes(data, graph, attrContOrder, attrDiscOrder, projections = None):
	if data.domain.classVar.varType != orange.VarTypes.Discrete:
		return ([attr.name for attr in data.domain.attributes], [])

	shown = []; hidden = []	# initialize outputs

	# # both are RELIEF
	if attrContOrder == "ReliefF" and attrDiscOrder == "ReliefF":
		newAttrs = orngFSS.attMeasure(data, orange.MeasureAttribute_relief(k=20, m=50))
		for item in newAttrs:
			if float(item[1]) > 0.1:   shown.append(item[0])
			else:					   hidden.append(item[0])
		return (shown, hidden)

	# # both are NONE
	elif attrContOrder == "None" and attrDiscOrder == "None":
		for item in data.domain.attributes:	shown.append(item.name)
		return (shown, hidden)

	# # both are VizRank
	elif attrContOrder == "VizRank" and attrDiscOrder == "VizRank":
		if projections:	return optimizeOrderVizRank(data, [attr.name for attr in data.domain.attributes], projections)
		else:
			print "VizRank projections have not been loaded. unable to use this heuristics. showing all attributes"
			return ([attr.name for attr in data.domain.attributes], [])

	# disc and cont attribute list
	discAttrs = []; contAttrs = []
	for attr in data.domain.attributes:
		if attr.varType == orange.VarTypes.Continuous: contAttrs.append(attr.name)
		elif attr.varType == orange.VarTypes.Discrete: discAttrs.append(attr.name)
		

	###############################
	# sort continuous attributes
	if attrContOrder == "None":
		shown = contAttrs
	elif attrContOrder == "ReliefF":
		newAttrs = orngFSS.attMeasure(data, orange.MeasureAttribute_relief())
		for (attr, val) in newAttrs:
			if attr in contAttrs:
				if val > 0.1: shown.append(attr)
				else: hidden.append(attr)

	elif attrContOrder == "Correlation":
		(shown, hidden) = optimizeOrderCorrelation(data, contAttrs)	# get the list of continuous attributes sorted by using correlation
	elif attrContOrder == "Fisher discriminant" and data.domain.classVar:
		contData = data.select(contAttrs + [data.domain.classVar.name])
		vals = orngFSS.attMeasure(contData, MeasureFisherDiscriminant())
		sum = 0.0
		for (att, val) in vals: sum += val
		tempSum = 0
		for (att, val) in vals:
			if tempSum/sum < 0.9: shown.append(att)
			else: hidden.append(att)
			tempSum += val
		return (shown, hidden)
	elif attrContOrder == "VizRank":
		if projections:
			(shown, hidden) = optimizeOrderVizRank(data, contAttrs, projections)
		else:
			print "VizRank projections have not been loaded. unable to use this heuristics. showing all attributes"
			shown = contAttrs
	else:
		print "Unknown value for attribute order: ", attrContOrder

	# ###############################
	# sort discrete attributes
	if attrDiscOrder == "None":
		shown += discAttrs
	elif attrDiscOrder == "ReliefF":
		newAttrs = orngFSS.attMeasure(data, orange.MeasureAttribute_relief())
		for (attr, val) in newAttrs:
			if attr in discAttrs:
				if val > 0.1: shown.append(attr)
				else: hidden.append(attr)

	elif attrDiscOrder == "GainRatio" or attrDiscOrder == "Gini":
		if attrDiscOrder == "GainRatio":   measure = orange.MeasureAttribute_gainRatio()
		else:							   measure = orange.MeasureAttribute_gini()

		dataNew = data.select(discAttrs)
		newAttrs = orngFSS.attMeasure(dataNew, measure)
		for item in newAttrs:
				shown.append(item[0])

	elif attrDiscOrder == "Oblivious decision graphs":
			shown.append(data.domain.classVar.name)
			attrs = getFunctionalList(data)
			for item in attrs:
				shown.append(item)
			for attr in data.domain.attributes:
				if attr.name not in shown and attr.varType == orange.VarTypes.Discrete:
					hidden.append(attr.name)
	elif attrContOrder == "VizRank":
		if projections:
			(s, h) = optimizeOrderVizRank(data, discAttrs, projections)
			shown += s;  hidden += h
		else:
			print "VizRank projections have not been loaded. unable to use this heuristics. showing all attributes"
			shown += discAttrs
	else:
		print "Unknown value for attribute order: ", attrDiscOrder

	#################################
	# if class attribute hasn't been added yet, we add it
	if data.domain.classVar.name not in shown + hidden:
		shown.append(data.domain.classVar.name)
	return (shown, hidden)

# create such a list of attributes, that attributes with interesting scatterplots lie together
def optimizeOrderVizRank(data, attrs, projections):
	list = []
	for (val, [a1, a2]) in projections:
		if a1 in attrs and a2 in attrs: list.append([val, a1, a2])
	shown = orderAttributes(data, list)
	hidden = []
	for attr in attrs:
		if attr not in shown: hidden.append(attr)
	return (shown, hidden)

# create such a list of attributes, that attributes with high correlation lie together
def optimizeOrderCorrelation(data, contAttrs):
	# create ordinary list of data values
	minCorrelation = 0.3
	
	# compute the correlations between attributes
	correlations = []
	for i in range(len(contAttrs)):
		for j in range(i+1, len(contAttrs)):
			table = data.select([contAttrs[i], contAttrs[j]])
			table = orange.Preprocessor_dropMissing(table)
			attr1 = [table[k][contAttrs[i]].value for k in range(len(table))]
			attr2 = [table[k][contAttrs[j]].value for k in range(len(table))]
			val, prob = statc.pearsonr(attr1, attr2)
			correlations.append([abs(val), contAttrs[i], contAttrs[j]])

	correlations.sort()
	correlations.reverse()
	mergedCorrs = []
	i = 0
	while correlations[i][0] > minCorrelation: i+=1
	shown = orderAttributes(data, correlations[:i])
	hidden = []
	for attr in contAttrs:
		if attr not in shown: hidden.append(attr)
	return (shown, hidden)


def orderAttributes(data, items):
	retGroups = []
	if len(items) > 0:
		retGroups.append([items[0][1], items[0][2]])
		items = items[1:]
		
	for [val, a1, a2] in items:
		if fixedMidPos(retGroups, a1) or fixedMidPos(retGroups, a2) or fixedEndPos(retGroups, a1, a2): continue
		for i in range(len(retGroups)):
			group = retGroups[i]
			if   a1 == group[0] : group = [a2] + group
			elif a2 == group[0]: group  = [a1] + group
			elif a1 == group[-1]: group = group + [a2]
			elif a2 == group[-1]: group = group + [a1]
			retGroups[i] = group

		# merge groups if they are mergable
		for i in range(len(retGroups)):
			j = i+1
			while j < len(retGroups):
				if retGroups[i][0] == retGroups[j][0]:
					retGroups[j].reverse()
					group = retGroups[j] + retGroups[i][1:]
				elif retGroups[i][-1] == retGroups[j][-1]:
					retGroups[j].reverse()
					group = retGroups[i] + retGroups[i][1:]
				elif retGroups[i][0] == retGroups[j][-1]:
					group = retGroups[j] + retGroups[i][1:]
				elif retGroups[i][-1] == retGroups[j][0]:
					group = retGroups[i] + retGroups[j][1:]
				else:
					j+=1
					continue
				retGroups.remove(retGroups[j])
				retGroups[i] = group

	attrs = []
	for gr in retGroups:
		attrs += gr

	return attrs


def fixedMidPos(array, val):
	for arr in array:
		if val in arr[1:-1]: return 1
	return 0

def fixedEndPos(array, a1, a2):
	for arr in array:
		if (arr[0] == a1 and arr[-1] == a2) or (arr[0] == a2 and arr[-1] == a1): return 1
	return 0


