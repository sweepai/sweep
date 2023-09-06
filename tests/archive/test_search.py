from sweepai.utils.search_and_replace import find_best_match

old_file = r"""\
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:klipnotes/model/observation.dart';
import 'package:klipnotes/styles.dart';
import 'package:klipnotes/ui/projects/newobservation.dart';
import 'package:klipnotes/utils/localdb.dart';
import 'package:path_provider/path_provider.dart';

class ViewCategory extends StatefulWidget {
  const ViewCategory(this.categoryRef, this.categoryData, this.reportName,
      {Key? key})
      : super(key: key);

  final DocumentReference categoryRef;
  final Map<String, dynamic>? categoryData;
  final String? reportName;

  @override
  ViewCategoryState createState() => ViewCategoryState();
}

class ViewCategoryState extends State<ViewCategory> {
  String? projectID;
  String? reportID;
  String? categoryID;

  late Directory directory;

  @override
  void initState() {
    super.initState();
    FirebaseAnalytics.instance.setCurrentScreen(screenName: 'view_category');

    final List<String> parts = widget.categoryRef.path.split('/');
    debugPrint(parts.join('/'));
    if (parts.length == 6) {
      projectID = parts[1];
      reportID = parts[3];
      categoryID = parts[5];
    }

    _initAsync();
  }

  Future<void> _initAsync() async {
    directory = await getApplicationDocumentsDirectory();
  }

  void _addNewObservation() {
    Navigator.of(context, rootNavigator: true).push(
      CupertinoPageRoute<NewObservation>(
        builder: (BuildContext context) {
          return NewObservation(widget.categoryRef, null, null);
        },
        fullscreenDialog: true,
      ),
    );
  }

  Widget _newObservationRow() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 8, 0),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              GestureDetector(
                onTap: _addNewObservation,
                child: Container(
                  width: 92,
                  height: 92,
                  color: const Color(0xfff1f1f1),
                  child: const Center(
                    child: Icon(
                      Icons.add,
                      color: Color(0xffc4c4c4),
                    ),
                  ),
                ),
              ),
              Center(
                child: CupertinoButton(
                  onPressed: _addNewObservation,
                  child: const Text('Add observation'),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(
              left: 100,
              top: 8,
            ),
            child: Container(
              height: 1,
              color: Styles.dividerBarColor,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _editObservation(
      DocumentSnapshot<Map<String, dynamic>> observation) async {
    Navigator.of(context, rootNavigator: true).push(
      CupertinoPageRoute<Map<String, dynamic>>(
        builder: (BuildContext context) {
          return NewObservation(
              widget.categoryRef, observation.reference, observation.data());
        },
        fullscreenDialog: true,
      ),
    );
  }

  Widget _getImageForCategory(
      DocumentSnapshot<Map<String, dynamic>> observationDoc) {
    Widget imageChild;
    final String thumbURL = observationDoc.data()!['thumb_url'] as String;

    if (thumbURL.isNotEmpty) {
      imageChild = CachedNetworkImage(
        imageUrl: thumbURL,
        imageBuilder: (BuildContext context, ImageProvider imageProvider) {
          return Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4.0),
              image: DecorationImage(
                image: imageProvider,
                fit: BoxFit.cover,
              ),
            ),
          );
        },
      );
    } else {
      final String? id = observationDoc.data()!['local_id'] as String?;
      imageChild = FutureBuilder<Observation?>(
        future: LocalDB.instance.getObservationFromID(id),
        builder: (BuildContext context, AsyncSnapshot<Observation?> snapshot) {
          if (snapshot.hasData) {
            final File observationFile =
                File('${directory.path}/${snapshot.data!.thumbLocalPath}');
            return Image.file(observationFile,
                height: 240, fit: BoxFit.scaleDown);
          }
          return const CircularProgressIndicator();
        },
      );
    }

    return SizedBox(
      width: 92,
      height: 92,
      child: imageChild,
    );
  }

  Widget _deleteContainer() {
    return Container(
      alignment: Alignment.centerLeft,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          const Icon(Icons.delete, color: Colors.white),
          Container(
            margin: const EdgeInsets.only(top: 8),
            child: const Text(
              'Delete',
              style: TextStyle(color: Colors.white),
            ),
          ),
        ],
      ),
    );
  }

  Future<bool> _confirmObservationDelete(
      DocumentSnapshot<Map<String, dynamic>> doc) async {
    final bool? confirmation = await showCupertinoDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return CupertinoAlertDialog(
          title: const Text('Delete Observation'),
          content: const Text(
            'Are you sure you want to delete this observation? This action cannot be reversed.',
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () {
                Navigator.of(context).pop(true);
              },
              child: const Text('Delete Observation'),
            ),
            CupertinoDialogAction(
              child: const Text('Cancel'),
              onPressed: () {
                Navigator.of(context).pop(false);
              },
            ),
          ],
        );
      },
    );

    if (confirmation == true) {
      // Set the 'is_active' to false on the observation
      await FirebaseFirestore.instance
          .doc(doc.reference.path)
          .set(<String, dynamic>{'is_active': false}, SetOptions(merge: true));
      // Decrement the category's observation_count, if this was visible
      final bool isHidden = doc.data()!['is_hidden'] ?? false;
      if (!isHidden) {
        final DocumentReference categoryRef = FirebaseFirestore.instance.doc(
            'projects/$projectID/reports/$reportID/categories/$categoryID');
        categoryRef.set(<String, dynamic>{
          'observation_count': FieldValue.increment(-1),
        }, SetOptions(merge: true));
      }

      // TODO Update the category's last_observation_url to the last valid observation now, if we need to change
      // TODO Update the report's first_observation_url to the next most valid observation now, if we need to change
    }

    return confirmation == true;
  }

  SliverChildBuilderDelegate _categoryList(
      AsyncSnapshot<QuerySnapshot<Map<String, dynamic>>> snap) {
    return SliverChildBuilderDelegate(
      (BuildContext context, int index) {
        final DocumentSnapshot<Map<String, dynamic>> doc =
            snap.data!.docs[index];

        final bool isHidden = doc.data()!['is_hidden'] ?? false;

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            _editObservation(doc);
          },
          child: Dismissible(
            key: Key(doc.id),
            direction: DismissDirection.horizontal,
            confirmDismiss: (DismissDirection direction) async {
              if (direction == DismissDirection.startToEnd) {
                return await _confirmObservationDelete(doc);
              } else {
                await FirebaseFirestore.instance
                    .doc(doc.reference.path)
                    .set(<String, dynamic>{
                  'is_hidden': !isHidden, // toggle it
                }, SetOptions(merge: true));
                await doc.reference.get();

                // Update the category's observation_count, increment when showing, decrement when hiding
                final DocumentReference categoryRef = FirebaseFirestore.instance
                    .doc(
                        'projects/$projectID/reports/$reportID/categories/$categoryID');
                categoryRef.set(<String, dynamic>{
                  'observation_count': FieldValue.increment(
                      isHidden ? 1 : -1), // increment or decrement
                }, SetOptions(merge: true));

                return false;
              }
            },
            secondaryBackground: Container(
              color: const Color(0xfff1f1f1),
              alignment: Alignment.centerRight,
              child: Padding(
                padding: const EdgeInsets.all(8.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(isHidden ? Icons.visibility : Icons.visibility_off,
                        color: const Color(0xff4f4f4f)),
                    const SizedBox(height: 8),
                    Text(
                      isHidden ? 'Show in report' : 'Hide from report',
                      style: const TextStyle(color: Color(0xff4f4f4f)),
                    ),
                  ],
                ),
              ),
            ),
            background: Container(
              color: Colors.red,
              child: _deleteContainer(),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 8, 0),
              child: Column(
                children: <Widget>[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      _getImageForCategory(doc),
                      Padding(
                        padding: const EdgeInsets.only(left: 14.0, top: 20),
                        child: SizedBox(
                          width: MediaQuery.of(context).size.width - 146,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              const Text(
                                'Observation',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Color(0xff6c6c6c),
                                ),
                              ),
                              Row(
                                children: <Widget>[
                                  Expanded(
                                    child: Text(
                                      doc.data()!['name'] as String,
                                      style: const TextStyle(fontSize: 16),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  if (isHidden)
                                    const Icon(
                                      Icons.visibility_off,
                                      color: Color(0xffbdbdbd),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                  Padding(
                    padding: const EdgeInsets.only(
                      left: 100,
                      top: 8,
                    ),
                    child: Container(
                      height: 1,
                      color: Styles.dividerBarColor,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
      childCount: snap.data!.docs.length,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white,
      child: CustomScrollView(
        slivers: <Widget>[
          CupertinoSliverNavigationBar(
            previousPageTitle: widget.reportName,
            largeTitle: Text(widget.categoryData!['name'] as String),
          ),
          SliverToBoxAdapter(
            child: _newObservationRow(),
          ),
          StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
            stream: FirebaseFirestore.instance
                .collection(
                    'projects/$projectID/reports/$reportID/categories/$categoryID/observations')
                .where('is_active', isEqualTo: true)
                .orderBy('sort_order', descending: false)
                .snapshots(),
            builder: (BuildContext context,
                AsyncSnapshot<QuerySnapshot<Map<String, dynamic>>> snapshot) {
              if (snapshot.hasError) return Text('Error: ${snapshot.error}');
              switch (snapshot.connectionState) {
                case ConnectionState.waiting:
                  return const SliverToBoxAdapter(
                      child: Center(child: Text('Loading...')));
                default:
                  return SliverReorderableList(

                    delegate: _categoryList(snapshot),
                    onReorder: (int oldIndex, int newIndex) {
                      setState(() {
                        if (oldIndex < newIndex) {
                          newIndex -= 1;
                        }
                        final DocumentSnapshot<Map<String, dynamic>> item = snapshot.data!.docs.removeAt(oldIndex);
                        snapshot.data!.docs.insert(newIndex, item);
          
                        // Update the sort_order field in Firestore
                        for (int i = 0; i < snapshot.data!.docs.length; i++) {
                          snapshot.data!.docs[i].reference.update({'sort_order': i});
                        }
                      });
                    },
                  );
              }
            },
          ),
          const SliverPadding(
            padding: EdgeInsets.only(bottom: 60),
          ),
        ],
      ),
    );
  }
}
"""


target = """\
    display={menuDisplay}
  />
  <MenuList\
"""

target = """\
  >
    {navItems.map((item) => (\
"""

target = """\
</ButtonGroup>
<Menu>
  <MenuButton"""

target = """\
SliverReorderableList(
  delegate: _categoryList(snapshot),
  onReorder: (int oldIndex, int newIndex) {
    setState(() {
      if (oldIndex < newIndex) {
        newIndex -= 1;
      }
      final DocumentSnapshot<Map<String, dynamic>> item = snapshot.data!.docs.removeAt(oldIndex);
      snapshot.data!.docs.insert(newIndex, item);

      // Update the sort_order field in Firestore
      for (int i = 0; i < snapshot.data!.docs.length; i++) {
        snapshot.data!.docs[i].reference.update({'sort_order': i});
      }
    });
  },
)
"""

best_match = find_best_match(target, old_file)
print(old_file.splitlines()[best_match.start:best_match.end + 1])
